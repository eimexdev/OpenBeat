import json
import os
import unittest
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from openbeat.analysis import BeatAnalysis, cache_path, load_or_analyze


class CacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.audio = self.root / "song.wav"
        self.audio.write_bytes(b"audio is mocked in cache tests")
        self.cache_dir = self.root / "cache"
        self.target = cache_path(str(self.audio), self.cache_dir)
        self.analysis = BeatAnalysis(str(self.audio.resolve()), 2.0, 22050, [0.1, 0.6, 1.1], 120.0, 0.1, [0.1, 0.6, 1.1, 1.6])

    def test_valid_cache_avoids_reanalysis(self) -> None:
        self.target.write_text(json.dumps(asdict(self.analysis)), encoding="utf-8")
        with mock.patch("openbeat.analysis.analyze_audio") as analyze:
            self.assertEqual(load_or_analyze(str(self.audio), self.cache_dir), self.analysis)
        analyze.assert_not_called()

    def test_invalid_cache_is_reanalyzed_and_replaced(self) -> None:
        invalid = ["{", "[]", "{}"]
        for field, value in (
            ("raw_beats", [float("nan")]), ("raw_beats", [0.6, 0.1]),
            ("raw_beats", []), ("raw_beats", [3]), ("raw_beats", [True]),
            ("duration_seconds", -1), ("tempo_bpm", 0), ("tempo_bpm", float("inf")),
            ("sample_rate", "22050"), ("sample_rate", 44100), ("audio_path", "other.wav"),
            ("grid_offset_seconds", "0.1"), ("quantized_beats", [0.1, 0.8]),
        ):
            payload = asdict(self.analysis)
            payload[field] = value
            invalid.append(json.dumps(payload))
        for payload in invalid:
            with self.subTest(payload=payload):
                self.target.write_text(payload, encoding="utf-8")
                with mock.patch("openbeat.analysis.analyze_audio", return_value=self.analysis) as analyze:
                    self.assertEqual(load_or_analyze(str(self.audio), self.cache_dir), self.analysis)
                analyze.assert_called_once_with(str(self.audio.resolve()), target_sr=22050)
                self.assertEqual(json.loads(self.target.read_text()), asdict(self.analysis))
                self.assertEqual(list(self.cache_dir.glob("*.tmp")), [])

    def test_cache_directory_failure_does_not_block_analysis(self) -> None:
        with mock.patch.object(Path, "mkdir", side_effect=PermissionError("read-only cache")):
            with mock.patch("openbeat.analysis.analyze_audio", return_value=self.analysis):
                self.assertEqual(load_or_analyze(str(self.audio), self.cache_dir), self.analysis)

    def test_failed_atomic_replace_preserves_old_file_and_cleans_temporary(self) -> None:
        self.target.write_text("old incomplete cache", encoding="utf-8")
        with mock.patch("openbeat.analysis.os.replace", side_effect=OSError("disk failure")):
            with mock.patch("openbeat.analysis.analyze_audio", return_value=self.analysis):
                self.assertEqual(load_or_analyze(str(self.audio), self.cache_dir), self.analysis)
        self.assertEqual(self.target.read_text(), "old incomplete cache")
        self.assertEqual(list(self.cache_dir.glob("*.tmp")), [])

    def test_final_cache_is_replaced_only_after_complete_json_is_written(self) -> None:
        self.target.write_text("old incomplete cache", encoding="utf-8")
        replace = os.replace

        def check_replace(source: Path, target: Path) -> None:
            self.assertEqual(target.read_text(), "old incomplete cache")
            self.assertEqual(json.loads(source.read_text()), asdict(self.analysis))
            replace(source, target)

        with mock.patch("openbeat.analysis.os.replace", side_effect=check_replace):
            with mock.patch("openbeat.analysis.analyze_audio", return_value=self.analysis):
                load_or_analyze(str(self.audio), self.cache_dir)
        self.assertEqual(json.loads(self.target.read_text()), asdict(self.analysis))

    def test_missing_source_is_still_reported(self) -> None:
        with mock.patch("openbeat.analysis.analyze_audio") as analyze:
            with self.assertRaises(FileNotFoundError):
                load_or_analyze(str(self.root / "missing.wav"), self.cache_dir)
        analyze.assert_not_called()


if __name__ == "__main__":
    unittest.main()
