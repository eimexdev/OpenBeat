from __future__ import annotations

import hashlib
import json
import math
import os
import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import librosa
import numpy as np

from openbeat import __version__


ANALYSIS_TARGET_SR = 22050
CACHE_SCHEMA_VERSION = "3"


@dataclass(slots=True)
class BeatAnalysis:
    audio_path: str
    duration_seconds: float
    sample_rate: int
    raw_beats: list[float]
    tempo_bpm: float
    grid_offset_seconds: float
    quantized_beats: list[float]


def estimate_grid(raw_beats: list[float]) -> tuple[float, float]:
    times = np.asarray(raw_beats, dtype=float)
    if not np.isfinite(times).all() or (times < 0).any() or (np.diff(times) <= 0).any():
        raise ValueError("Beat times must be finite, nonnegative, and strictly increasing")
    if len(raw_beats) < 2:
        if not raw_beats:
            return 120.0, 0.0
        return 120.0, raw_beats[0]

    intervals = np.diff(times)
    seed_period = float(np.median(intervals))
    # Preserve missing beats as gaps in the beat numbers, rather than slowing the grid.
    steps = np.maximum(1, np.rint(intervals / seed_period))
    numbers = np.concatenate(([0.0], np.cumsum(steps)))
    inliers = np.ones(len(times), dtype=bool)
    period = seed_period
    offset = float(times[0])
    for _ in range(5):
        x, y = numbers[inliers], times[inliers]
        centered = x - x.mean()
        period = float(np.dot(centered, y - y.mean()) / np.dot(centered, centered))
        offset = float(np.median(y - x * period))
        residuals = times - (offset + numbers * period)
        center = float(np.median(residuals))
        spread = float(np.median(np.abs(residuals - center)))
        candidates = np.abs(residuals - center) <= max(0.03, 4.0 * 1.4826 * spread)
        if candidates.sum() < 2 or np.array_equal(candidates, inliers):
            break
        inliers = candidates

    phase = offset % period
    if math.isclose(phase, period, abs_tol=1e-9):
        phase = 0.0
    return 60.0 / period, phase


def quantized_beats(tempo_bpm: float, offset_seconds: float, duration_seconds: float) -> list[float]:
    if tempo_bpm <= 0:
        return []
    beats: list[float] = []
    period = 60.0 / tempo_bpm
    current = offset_seconds
    while current <= duration_seconds:
        beats.append(current)
        current += period
    return beats


def analyze_audio(audio_path: str, target_sr: int = ANALYSIS_TARGET_SR) -> BeatAnalysis:
    audio_path = str(Path(audio_path).expanduser().resolve())
    signal, sr = librosa.load(audio_path, sr=target_sr, mono=True)
    duration_seconds = float(librosa.get_duration(y=signal, sr=sr))
    _, beat_frames = librosa.beat.beat_track(y=signal, sr=sr, trim=False)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    beat_times = [float(value) for value in beat_times]

    if not beat_times:
        raise RuntimeError(f"No beats detected in {audio_path}")

    tempo_bpm, grid_offset = estimate_grid(beat_times)
    return BeatAnalysis(
        audio_path=audio_path,
        duration_seconds=duration_seconds,
        sample_rate=sr,
        raw_beats=beat_times,
        tempo_bpm=tempo_bpm,
        grid_offset_seconds=grid_offset,
        quantized_beats=quantized_beats(tempo_bpm, grid_offset, duration_seconds),
    )


def default_cache_dir() -> Path:
    home = Path.home()
    system = sys_platform()
    if system == "darwin":
        return home / "Library" / "Caches" / "OpenBeat"

    if system == "windows":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "OpenBeat" / "Cache"
        return home / "AppData" / "Local" / "OpenBeat" / "Cache"

    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache_home:
        return Path(xdg_cache_home) / "openbeat"

    return home / ".cache" / "openbeat"


def sys_platform() -> str:
    return platform.system().lower()


def cache_key(audio_path: str, target_sr: int = ANALYSIS_TARGET_SR) -> str:
    path = Path(audio_path).expanduser().resolve()
    stat = path.stat()
    payload = json.dumps(
        {
            "path": str(path),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "target_sr": target_sr,
            "cache_schema": CACHE_SCHEMA_VERSION,
            "openbeat_version": __version__,
            "librosa_version": librosa.__version__,
        },
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def cache_path(audio_path: str, cache_dir: Path | None = None, target_sr: int = ANALYSIS_TARGET_SR) -> Path:
    cache_dir = cache_dir or default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{cache_key(audio_path, target_sr=target_sr)}.json"


def load_or_analyze(
    audio_path: str,
    cache_dir: Path | None = None,
    target_sr: int = ANALYSIS_TARGET_SR,
) -> BeatAnalysis:
    target = cache_path(audio_path, cache_dir, target_sr=target_sr)
    if target.exists():
        return BeatAnalysis(**json.loads(target.read_text()))

    analysis = analyze_audio(audio_path, target_sr=target_sr)
    target.write_text(json.dumps(asdict(analysis), indent=2))
    return analysis


def to_lua(value: Any) -> str:
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    if isinstance(value, list):
        inner = ", ".join(to_lua(item) for item in value)
        return "{ " + inner + " }"
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            parts.append(f"{key} = {to_lua(item)}")
        return "{\n  " + ",\n  ".join(parts) + "\n}"
    raise TypeError(f"Unsupported value for Lua serialization: {type(value)!r}")


def write_lua_analysis(analysis: BeatAnalysis, output_path: str) -> None:
    payload = asdict(analysis)
    Path(output_path).write_text("return " + to_lua(payload) + "\n")
