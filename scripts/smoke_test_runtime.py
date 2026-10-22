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


def test_signal(sample_rate: int = 22050) -> np.ndarray:
    """16 seconds of clicks at 120 BPM, the first at 0.2 seconds."""
    signal = np.zeros(16 * sample_rate, dtype=np.float32)
    time = np.arange(int(0.03 * sample_rate)) / sample_rate
    click = np.sin(2 * np.pi * 1800 * time) * np.exp(-time * 55)
    for beat in 0.2 + np.arange(32) * 0.5:
        start = round(float(beat) * sample_rate)
        signal[start : start + len(click)] += click
    return signal


def write_test_audio(path: Path, format: str | None = None) -> None:
    sf.write(path, test_signal(), 22050, format=format)


def write_test_media(
    path: Path,
    audio_codec: str = "aac",
    with_video: bool = False,
    audio_offset: float = 0.0,
    gap: tuple[float, float] | None = None,
) -> None:
    """Encode the test signal with PyAV's FFmpeg, like a phone recording or camera clip.

    ``audio_offset`` starts the audio that many seconds after the video; ``gap`` drops
    the audio between two times, leaving a jump in its timestamps.
    """
    import av

    sample_rate = 48000
    stereo = np.tile(test_signal(sample_rate), (2, 1))
    offset = round(audio_offset * sample_rate)
    with av.open(str(path), "w") as container:
        video = None
        if with_video:
            video = container.add_stream("mpeg4", rate=25)
            video.width, video.height, video.pix_fmt = 64, 64, "yuv420p"
        audio = container.add_stream(audio_codec, rate=sample_rate, layout="stereo")
        for start in range(0, stereo.shape[1], 1024):
            if gap is not None and gap[0] * sample_rate <= start < gap[1] * sample_rate:
                continue
            chunk = stereo[:, start : start + 1024]
            if audio_codec == "aac":
                frame = av.AudioFrame.from_ndarray(np.ascontiguousarray(chunk), format="fltp", layout="stereo")
            else:
                pcm = (np.clip(chunk, -1, 1) * 32767).astype(np.int16).T.reshape(1, -1)
                frame = av.AudioFrame.from_ndarray(pcm, format="s16", layout="stereo")
            frame.sample_rate, frame.pts = sample_rate, start + offset
            container.mux(audio.encode(frame))
        container.mux(audio.encode(None))
        if video is not None:
            for index in range(round((16 + audio_offset) * 25)):
                picture = av.VideoFrame(64, 64, "yuv420p")
                picture.pts = index
                container.mux(video.encode(picture))
            container.mux(video.encode(None))


def verify_runtime(command: list[str]) -> dict:
    with tempfile.TemporaryDirectory(prefix="openbeat-smoke-") as temporary:
        work_dir = Path(temporary)
        audio = work_dir / "test music 音楽.wav"
        write_test_audio(audio)
        cache_files = [default_cache_dir() / f"{cache_key(str(audio))}.json"]

        def run(*args: str, expect_failure: bool = False) -> subprocess.CompletedProcess:
            result = subprocess.run(command + list(args), cwd=work_dir, text=True, capture_output=True, timeout=180)
            if bool(result.returncode) != expect_failure:
                raise RuntimeError(f"Runtime exited {result.returncode}: {result.stdout}\n{result.stderr}")
            return result

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

            # MP3 relies on the bundled libsndfile, and M4A and video files on the FFmpeg
            # libraries bundled with PyAV, so prove each decodes in the built runtime.
            sources = {"test music.mp3": lambda path: write_test_audio(path, format="MP3")}
            sources["phone memo.m4a"] = write_test_media
            sources["camera clip.mov"] = lambda path: write_test_media(path, "pcm_s16le", with_video=True)
            sources["screen recording.mp4"] = lambda path: write_test_media(path, with_video=True)
            for name, write in sources.items():
                source = work_dir / name
                write(source)
                cache_files.append(default_cache_dir() / f"{cache_key(str(source))}.json")
                result_file = work_dir / f"{source.stem}.json"
                run("analyze", "--audio", str(source), "--output", str(result_file))
                decoded = json.loads(result_file.read_text(encoding="utf-8"))
                if not 119 <= decoded["tempo_bpm"] <= 121 or abs(decoded["duration_seconds"] - 16) > 0.1:
                    raise AssertionError(f"Unexpected analysis of {name}: {decoded}")
                period = 60 / decoded["tempo_bpm"]
                if abs((decoded["grid_offset_seconds"] - 0.2 + period / 2) % period - period / 2) > 0.05:
                    raise AssertionError(f"Beat phase of {name} is off: {decoded['grid_offset_seconds']}")

            # Unreadable sources must fail with a plain message rather than a traceback.
            for name in ("clip.m4a", "corrupt.wav"):
                (work_dir / name).write_bytes(b"\0" * 4096)
                result = run("analyze", "--audio", str(work_dir / name), "--output", "unused.json", expect_failure=True)
                if "OpenBeat reads audio files" not in result.stderr or "Traceback" in result.stderr:
                    raise AssertionError(f"Unclear error for {name}: {result.stderr}")
            return analysis
        finally:
            for cache_file in cache_files:
                cache_file.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime", type=Path)
    args = parser.parse_args()
    analysis = verify_runtime([str(args.runtime.resolve())])
    print(f"Runtime smoke test passed: {len(analysis['raw_beats'])} beats, {analysis['tempo_bpm']:.3f} BPM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
