import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import soundfile as sf
import numpy as np

from openbeat.analysis import cache_key, default_cache_dir, estimate_grid, quantized_beats
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

    def test_fractional_tempos_stay_aligned_over_three_minutes(self) -> None:
        for tempo in (37.3, 120.5, 127.3, 180.25):
            with self.subTest(tempo=tempo):
                times = 0.2 + np.arange(int(180 * tempo / 60)) * (60 / tempo)
                bpm, offset = estimate_grid(times.tolist())
                self.assertAlmostEqual(bpm, tempo, places=8)
                self.assertAlmostEqual(offset, 0.2, places=8)
                grid = np.asarray(quantized_beats(bpm, offset, float(times[-1]) + 0.01))
                self.assertLess(float(np.max(np.abs(grid - times))), 1e-8)

    def test_grid_handles_missing_beats_and_detection_jitter(self) -> None:
        rng = np.random.default_rng(10)
        numbers = np.asarray([i for i in range(360) if i % 7 != 3])
        times = 0.2 + numbers * (60 / 120.5) + rng.normal(0, 0.005, len(numbers))
        times[20] += 0.08
        bpm, offset = estimate_grid(times.tolist())
        self.assertLess(abs(bpm - 120.5), 0.01)
        expected = 0.2 + numbers * (60 / 120.5)
        fitted = offset + numbers * (60 / bpm)
        self.assertLess(float(np.max(np.abs(fitted - expected))), 0.003)

    def test_grid_rejects_invalid_beat_times(self) -> None:
        for beats in ([0.2, float("nan")], [0.2, float("inf")], [-1, 0], [1, 0], [0, 0]):
            with self.subTest(beats=beats), self.assertRaises(ValueError):
                estimate_grid(beats)

    def test_render_click_track_defaults_to_stereo(self) -> None:
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "clicks.wav"
            render_click_track(str(output), [0.1, 0.6], 1.0)
            waveform, sample_rate = sf.read(output)
        self.assertEqual(sample_rate, 48000)
        self.assertEqual(waveform.ndim, 2)
        self.assertEqual(waveform.shape[1], 2)

    def test_render_click_track_is_stable_across_block_sizes(self) -> None:
        with TemporaryDirectory() as tmpdir:
            large_blocks = Path(tmpdir) / "large-blocks.wav"
            small_blocks = Path(tmpdir) / "small-blocks.wav"
            beats = [0.01, 0.018, 0.42, 0.99]
            render_click_track(str(large_blocks), beats, 1.0, block_size=48000)
            render_click_track(str(small_blocks), beats, 1.0, block_size=257)
            large_waveform, large_sample_rate = sf.read(large_blocks)
            small_waveform, small_sample_rate = sf.read(small_blocks)

        self.assertEqual(large_sample_rate, small_sample_rate)
        self.assertEqual(large_waveform.shape, small_waveform.shape)
        self.assertTrue((large_waveform == small_waveform).all())

    def test_windows_cache_uses_local_appdata(self) -> None:
        with mock.patch("openbeat.analysis.platform.system", return_value="Windows"):
            with mock.patch.dict("os.environ", {"LOCALAPPDATA": "C:/Users/Parker/AppData/Local"}):
                self.assertEqual(
                    default_cache_dir(),
                    Path("C:/Users/Parker/AppData/Local") / "OpenBeat" / "Cache",
                )

    def test_cache_key_changes_with_analysis_version_inputs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            audio = Path(tmpdir) / "track.wav"
            audio.write_bytes(b"not real audio")

            with mock.patch("openbeat.analysis.__version__", "1.0.0"):
                first = cache_key(str(audio), target_sr=22050)

            with mock.patch("openbeat.analysis.__version__", "1.0.1"):
                second = cache_key(str(audio), target_sr=22050)

            with mock.patch("openbeat.analysis.__version__", "1.0.0"):
                third = cache_key(str(audio), target_sr=44100)

        self.assertNotEqual(first, second)
        self.assertNotEqual(first, third)


if __name__ == "__main__":
    unittest.main()
