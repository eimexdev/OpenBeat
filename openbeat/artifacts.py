from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import soundfile as sf

from .analysis import BeatAnalysis, load_or_analyze


def _click_kernel(sample_rate: int, length_seconds: float = 0.03) -> np.ndarray:
    length = max(1, int(sample_rate * length_seconds))
    time = np.arange(length, dtype=np.float32) / sample_rate
    tone = np.sin(2.0 * math.pi * 1800.0 * time)
    envelope = np.exp(-time * 55.0)
    transient = np.sin(2.0 * math.pi * 3200.0 * time) * np.exp(-time * 110.0)
    return (0.8 * tone + 0.35 * transient) * envelope


def render_click_track(
    output_path: str,
    beats: list[float],
    duration_seconds: float,
    sample_rate: int = 48000,
    stereo: bool = True,
) -> str:
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    total_samples = max(1, int(sample_rate * max(duration_seconds + 1.0, 1.0)))
    waveform = np.zeros(total_samples, dtype=np.float32)
    click = _click_kernel(sample_rate)

    for beat in beats:
        start = max(0, int(round(beat * sample_rate)))
        stop = min(total_samples, start + len(click))
        waveform[start:stop] += click[: stop - start]

    waveform = np.clip(waveform, -1.0, 1.0)
    output_data = np.column_stack((waveform, waveform)) if stereo else waveform
    sf.write(output, output_data, sample_rate, subtype="PCM_16")
    return str(output)


def create_click_track(
    audio_path: str,
    output_path: str,
    mode: str,
) -> tuple[str, BeatAnalysis]:
    analysis = load_or_analyze(audio_path)
    beats = analysis.quantized_beats if mode == "quantized" else analysis.raw_beats
    result = render_click_track(output_path, beats, analysis.duration_seconds)
    return result, analysis
