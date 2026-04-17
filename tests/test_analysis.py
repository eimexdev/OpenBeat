import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import soundfile as sf

from openbeat.analysis import estimate_grid, quantized_beats
from openbeat.artifacts import render_click_track


class AnalysisTests(unittest.TestCase):
    def test_estimate_grid_on_even_beats(self) -> None:
        beats = [0.2, 0.7, 1.2, 1.7, 2.2, 2.7]
        bpm, offset = estimate_grid(beats)
        self.assertEqual(round(bpm), 120)
        self.assertLess(abs(offset - 0.2), 0.02)

    def test_quantized_beats_extends_until_duration(self) -> None:
        beats = quantized_beats(120.0, 0.25, 1.3)
        self.assertEqual(beats, [0.25, 0.75, 1.25])

    def test_render_click_track_defaults_to_stereo(self) -> None:
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "clicks.wav"
            render_click_track(str(output), [0.1, 0.6], 1.0)
            waveform, sample_rate = sf.read(output)
        self.assertEqual(sample_rate, 48000)
        self.assertEqual(waveform.ndim, 2)
        self.assertEqual(waveform.shape[1], 2)


if __name__ == "__main__":
    unittest.main()
