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
    block_size: int = 48000,
) -> str:
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    total_samples = max(1, int(sample_rate * max(duration_seconds + 1.0, 1.0)))
    click = _click_kernel(sample_rate)
    click_length = len(click)
    block_size = max(1, int(block_size))

    click_starts: list[int] = []
    for beat in beats:
        start = int(round(beat * sample_rate))
        if start < total_samples:
            click_starts.append(max(0, start))
    click_starts.sort()

    channels = 2 if stereo else 1
    next_click = 0
    active_clicks: list[int] = []

    with sf.SoundFile(output, mode="w", samplerate=sample_rate, channels=channels, subtype="PCM_16") as wav:
        for block_start in range(0, total_samples, block_size):
            block_stop = min(total_samples, block_start + block_size)
            block = np.zeros(block_stop - block_start, dtype=np.float32)

            while next_click < len(click_starts) and click_starts[next_click] < block_stop:
                active_clicks.append(click_starts[next_click])
                next_click += 1

            remaining_clicks: list[int] = []
            for click_start in active_clicks:
                click_stop = click_start + click_length
                if click_stop <= block_start:
                    continue

                write_start = max(block_start, click_start)
                write_stop = min(block_stop, click_stop)
                if write_stop > write_start:
                    block_offset = write_start - block_start
                    click_offset = write_start - click_start
                    write_length = write_stop - write_start
                    block[block_offset : block_offset + write_length] += click[
                        click_offset : click_offset + write_length
                    ]

                remaining_clicks.append(click_start)

            active_clicks = remaining_clicks
            block = np.clip(block, -1.0, 1.0)
            output_data = np.column_stack((block, block)) if stereo else block
            wav.write(output_data)

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
