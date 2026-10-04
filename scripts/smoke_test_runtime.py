"""Exercise the actual CLI/runtime with generated audio, outside the checkout."""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from openbeat.analysis import cache_key, default_cache_dir


def write_test_audio(path: Path) -> None:
    sample_rate = 22050
    signal = np.zeros(16 * sample_rate, dtype=np.float32)
    time = np.arange(int(0.03 * sample_rate)) / sample_rate
    click = np.sin(2 * np.pi * 1800 * time) * np.exp(-time * 55)
    for beat in 0.2 + np.arange(32) * 0.5:
        start = round(float(beat) * sample_rate)
        signal[start : start + len(click)] += click
    sf.write(path, signal, sample_rate)


def verify_runtime(command: list[str]) -> dict:
    with tempfile.TemporaryDirectory(prefix="openbeat-smoke-") as temporary:
        work_dir = Path(temporary)
        audio = work_dir / "test music 音楽.wav"
        write_test_audio(audio)
        cache = default_cache_dir() / f"{cache_key(str(audio))}.json"

        def run(*args: str) -> None:
            result = subprocess.run(command + list(args), cwd=work_dir, text=True, capture_output=True, timeout=180)
            if result.returncode:
                raise RuntimeError(f"Runtime failed ({result.returncode}): {result.stdout}\n{result.stderr}")

        try:
            analysis_file = work_dir / "analysis.json"
            run("analyze", "--audio", str(audio), "--output", str(analysis_file))
            analysis = json.loads(analysis_file.read_text(encoding="utf-8"))
            if not 119 <= analysis["tempo_bpm"] <= 121 or len(analysis["raw_beats"]) < 25:
                raise AssertionError(f"Unexpected real-audio analysis: {analysis}")
            if abs(analysis["duration_seconds"] - 16) > 0.001 or analysis["audio_path"] != str(audio.resolve()):
                raise AssertionError("Analysis did not preserve source duration/path")
            period = 60 / analysis["tempo_bpm"]
            phase_error = abs((analysis["grid_offset_seconds"] - 0.2 + period / 2) % period - period / 2)
            if phase_error > 0.05:
                raise AssertionError(f"Beat phase differs by {phase_error:.3f}s")

            lua_file = work_dir / "analysis.lua"
            run("analyze", "--audio", str(audio), "--format", "lua", "--output", str(lua_file))
            lua = lua_file.read_text(encoding="utf-8")
            if not lua.startswith("return {") or "音楽" not in lua or "raw_beats" not in lua:
                raise AssertionError("Runtime did not produce its Lua transport format")

            for mode in ("raw", "quantized"):
                output = work_dir / f"{mode}.wav"
                run("click-track", "--audio", str(audio), "--mode", mode, "--output", str(output))
                waveform, sample_rate = sf.read(output)
                if sample_rate != 48000 or waveform.shape != (17 * 48000, 2):
                    raise AssertionError("Click track has incorrect rate, duration, or channels")
                if not np.array_equal(waveform[:, 0], waveform[:, 1]):
                    raise AssertionError("Click channels differ")
                beats = analysis["raw_beats"] if mode == "raw" else analysis["quantized_beats"]
                for beat in beats:
                    start = round(beat * sample_rate)
                    if np.max(np.abs(waveform[start : start + 1000, 0])) < 0.1:
                        raise AssertionError(f"Missing {mode} click at {beat:.3f}s")
            return analysis
        finally:
            cache.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime", type=Path)
    args = parser.parse_args()
    analysis = verify_runtime([str(args.runtime.resolve())])
    print(f"Runtime smoke test passed: {len(analysis['raw_beats'])} beats, {analysis['tempo_bpm']:.3f} BPM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
