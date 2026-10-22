from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import av
import librosa
import numpy as np
import soundfile as sf

from openbeat import __version__


ANALYSIS_TARGET_SR = 22050
CACHE_SCHEMA_VERSION = "4"

# libsndfile reads these directly; the bundled FFmpeg (through PyAV) reads everything
# else, including AAC/M4A and the audio tracks of video files, and is the fallback when
# libsndfile cannot decode a file with one of these extensions.
SNDFILE_EXTENSIONS = frozenset({".aif", ".aifc", ".aiff", ".bwf", ".flac", ".mp3", ".oga", ".ogg", ".wav", ".wave"})
READABLE_FORMATS = (
    "OpenBeat reads audio files such as WAV, AIFF, FLAC, MP3, M4A, and AAC, "
    "and the audio track of video files such as MOV, MP4, and MXF."
)


class AudioInputError(Exception):
    """A problem with the user's audio file, reported without a traceback."""


class AudioFileNotFoundError(AudioInputError, FileNotFoundError):
    pass


def _cannot_read(audio_path: str, reason: str) -> AudioInputError:
    return AudioInputError(f"Can't read audio from {audio_path}: {reason}\n{READABLE_FORMATS}")


def check_audio_source(audio_path: str) -> None:
    """Cheap upfront checks, before cache lookup or decoding."""
    if not Path(audio_path).is_file():
        raise AudioFileNotFoundError(f"Audio file not found: {audio_path}")


def _read_with_soundfile(audio_path: str) -> tuple[np.ndarray, int]:
    with sf.SoundFile(audio_path) as audio:
        return audio.read(dtype="float32", always_2d=True).T, audio.samplerate


# Timestamp differences smaller than this are rounding, not gaps or overlaps.
TIMESTAMP_TOLERANCE_SECONDS = 0.001
# Audio is never padded past the file's duration, or past this when the file has none:
# a later timestamp is treated as broken rather than as silence to insert.
MAX_TIMESTAMP_GAP_SECONDS = 600


def _mono_samples(frame: av.AudioFrame) -> np.ndarray:
    """The frame's samples as float32, mixed down by averaging channels like librosa.to_mono."""
    samples = frame.to_ndarray()
    if not frame.format.is_planar:
        samples = samples.reshape(-1, len(frame.layout.channels)).T
    if samples.dtype == np.uint8:
        samples = (samples.astype(np.float32) - 128) / 128
    elif np.issubdtype(samples.dtype, np.integer):
        samples = samples.astype(np.float32) / float(np.iinfo(samples.dtype).max + 1)
    return samples.astype(np.float32, copy=False).mean(axis=0)


def _read_with_ffmpeg(audio_path: str) -> tuple[np.ndarray, int]:
    """Decode the first audio track, placing each frame at its timestamp.

    Beat times are offsets into the source file, so audio that starts after the file's
    first video frame, or skips ahead, keeps its position on the media timeline.
    """
    try:
        container = av.open(audio_path)
    except av.FFmpegError as exc:
        raise _cannot_read(audio_path, "the file is damaged or is not an audio or video file.") from exc
    with container:
        if not container.streams.audio:
            raise _cannot_read(audio_path, "the file has no audio track.")
        stream = container.streams.audio[0]
        sr = stream.rate
        origin = container.start_time / av.time_base if container.start_time is not None else None
        tolerance = round(TIMESTAMP_TOLERANCE_SECONDS * sr)
        if container.duration:
            limit = round((container.duration / av.time_base + 1) * sr)
        else:
            limit = round(MAX_TIMESTAMP_GAP_SECONDS * sr)
        chunks = []
        position = 0  # Samples placed so far, from the origin.
        try:
            for frame in container.decode(stream):
                samples = _mono_samples(frame)
                if frame.time is not None:
                    if origin is None:
                        origin = frame.time
                    offset = round((frame.time - origin) * sr) - position
                    if offset > tolerance and position + offset <= limit:
                        chunks.append(np.zeros(offset, dtype=np.float32))
                        position += offset
                    elif offset < -tolerance:
                        # Overlaps earlier audio, or is preroll before the file starts.
                        samples = samples[-offset:]
                chunks.append(samples)
                position += len(samples)
        except av.FFmpegError as exc:
            raise _cannot_read(audio_path, "the audio track is damaged.") from exc
        if not chunks:
            raise AudioInputError(f"No audio samples found in {audio_path}")
        return np.concatenate(chunks)[np.newaxis, :], sr


def load_audio(audio_path: str, target_sr: int) -> tuple[np.ndarray, int]:
    channels = None
    if Path(audio_path).suffix.lower() in SNDFILE_EXTENSIONS:
        try:
            channels, sr = _read_with_soundfile(audio_path)
        except sf.SoundFileError:
            channels = None  # For example, a WAV with a codec libsndfile lacks; FFmpeg may read it.
    if channels is None:
        channels, sr = _read_with_ffmpeg(audio_path)
    # The same mixdown and resampling librosa.load applies.
    signal = librosa.to_mono(channels)
    if signal.size == 0:
        raise AudioInputError(f"No audio samples found in {audio_path}")
    if sr != target_sr:
        signal = librosa.resample(signal, orig_sr=sr, target_sr=target_sr)
    return np.ascontiguousarray(signal, dtype=np.float32), target_sr


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
    check_audio_source(audio_path)
    signal, sr = load_audio(audio_path, target_sr)
    duration_seconds = float(librosa.get_duration(y=signal, sr=sr))
    _, beat_frames = librosa.beat.beat_track(y=signal, sr=sr, trim=False)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    beat_times = [float(value) for value in beat_times]

    if not beat_times:
        raise AudioInputError(f"No beats detected in {audio_path}")

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
    key = cache_key(audio_path, target_sr=target_sr)
    cache_dir = cache_dir or default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{key}.json"


def _cached_analysis(payload: Any, audio_path: str, target_sr: int) -> BeatAnalysis:
    if not isinstance(payload, dict):
        raise ValueError("Invalid analysis cache object")
    analysis = BeatAnalysis(**payload)

    def finite_number(value: Any) -> bool:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        try:
            return math.isfinite(value)
        except OverflowError:
            return False

    if analysis.audio_path != audio_path or type(analysis.sample_rate) is not int or analysis.sample_rate != target_sr:
        raise ValueError("Analysis cache does not match the source")
    if not finite_number(analysis.duration_seconds) or analysis.duration_seconds <= 0:
        raise ValueError("Invalid cached duration")
    if not finite_number(analysis.tempo_bpm) or analysis.tempo_bpm <= 0:
        raise ValueError("Invalid cached tempo")
    if not finite_number(analysis.grid_offset_seconds) or not 0 <= analysis.grid_offset_seconds <= analysis.duration_seconds:
        raise ValueError("Invalid cached grid offset")
    for beats in (analysis.raw_beats, analysis.quantized_beats):
        if not isinstance(beats, list) or not beats:
            raise ValueError("Invalid cached beats")
        if not all(finite_number(beat) and 0 <= beat <= analysis.duration_seconds for beat in beats):
            raise ValueError("Invalid cached beat time")
        if any(left >= right for left, right in zip(beats, beats[1:])):
            raise ValueError("Cached beats must be strictly increasing")
    period = 60.0 / analysis.tempo_bpm
    if not math.isclose(analysis.quantized_beats[0], analysis.grid_offset_seconds, abs_tol=1e-7):
        raise ValueError("Cached grid does not match its offset")
    if any(not math.isclose(right - left, period, abs_tol=1e-7)
           for left, right in zip(analysis.quantized_beats, analysis.quantized_beats[1:])):
        raise ValueError("Cached grid does not match its tempo")
    if analysis.quantized_beats[-1] + period < analysis.duration_seconds - 1e-7:
        raise ValueError("Cached grid is incomplete")
    return analysis


def _write_cache(target: Path, analysis: BeatAnalysis) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, prefix=f".{target.stem}-", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(asdict(analysis), handle, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def load_or_analyze(
    audio_path: str,
    cache_dir: Path | None = None,
    target_sr: int = ANALYSIS_TARGET_SR,
) -> BeatAnalysis:
    audio_path = str(Path(audio_path).expanduser().resolve())
    check_audio_source(audio_path)
    # Source errors should still be reported; cache errors should not prevent analysis.
    key = cache_key(audio_path, target_sr=target_sr)
    target = None
    try:
        directory = cache_dir or default_cache_dir()
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{key}.json"
        return _cached_analysis(json.loads(target.read_text(encoding="utf-8")), audio_path, target_sr)
    except (OSError, UnicodeError, ValueError, TypeError):
        pass

    analysis = analyze_audio(audio_path, target_sr=target_sr)
    if target is not None:
        try:
            _write_cache(target, analysis)
        except OSError:
            pass
    return analysis


def to_lua(value: Any) -> str:
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("Lua numbers must be finite")
        return repr(value)
    if isinstance(value, str):
        escapes = { "\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t" }
        escaped = "".join(escapes.get(char, f"\\{ord(char):03d}" if ord(char) < 32 else char) for char in value)
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
    Path(output_path).write_text("return " + to_lua(payload) + "\n", encoding="utf-8")
