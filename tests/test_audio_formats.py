import contextlib
import io
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import soundfile as sf

from openbeat import analysis, cli
from openbeat.analysis import AudioInputError, analyze_audio, check_audio_source
from scripts.smoke_test_runtime import write_test_audio


def run_cli(*args: str) -> tuple[int, str]:
    stderr = io.StringIO()
    with TemporaryDirectory() as cache, mock.patch.dict("os.environ", {"XDG_CACHE_HOME": cache}):
        with mock.patch.object(sys, "argv", ["openbeat", *args]), contextlib.redirect_stderr(stderr):
            code = cli.main()
    return code, stderr.getvalue()


class AudioFormatTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)

    def test_unsupported_extension_reports_formats_and_suggestion(self) -> None:
        clip = self.dir / "interview.m4a"
        clip.write_bytes(b"\0" * 4096)
        code, stderr = run_cli("analyze", "--audio", str(clip), "--output", str(self.dir / "out.json"))

        self.assertEqual(code, 1)
        self.assertIn(str(clip), stderr)
        self.assertIn("can't decode .m4a files", stderr)
        self.assertIn("Supported formats: WAV, AIFF, FLAC, OGG Vorbis", stderr)
        self.assertIn("convert the audio to WAV or MP3", stderr)
        self.assertFalse((self.dir / "out.json").exists())

    def test_unsupported_extension_is_rejected_before_decoding_without_fallback(self) -> None:
        clip = self.dir / "clip.MOV"
        clip.write_bytes(b"\0" * 4096)
        with mock.patch.object(analysis, "_audioread_fallback", return_value=False):
            with mock.patch.object(analysis.librosa, "load") as load:
                with self.assertRaisesRegex(AudioInputError, r"can't decode \.mov files"):
                    analyze_audio(str(clip))
        load.assert_not_called()

    def test_corrupt_wav_reports_decode_failure(self) -> None:
        corrupt = self.dir / "song.wav"
        corrupt.write_bytes(b"RIFF\0\0\0\0WAVEjunk" * 64)
        code, stderr = run_cli("click-track", "--audio", str(corrupt), "--output", str(self.dir / "c.wav"))

        self.assertEqual(code, 1)
        self.assertIn(f"Can't read audio from {corrupt}", stderr)
        self.assertIn("damaged or not in a supported format", stderr)
        self.assertIn("Supported formats:", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_missing_and_empty_files_are_reported(self) -> None:
        with self.assertRaisesRegex(AudioInputError, "Audio file not found"):
            check_audio_source(str(self.dir / "missing.wav"))
        empty = self.dir / "empty.wav"
        sf.write(empty, [], 22050)
        with self.assertRaisesRegex(AudioInputError, "No audio samples"):
            analyze_audio(str(empty))

    def test_unexpected_errors_are_not_masked(self) -> None:
        audio = self.dir / "track.wav"
        write_test_audio(audio)
        with mock.patch.object(analysis.librosa, "load", side_effect=ValueError("boom")):
            with self.assertRaisesRegex(ValueError, "boom"):
                run_cli("analyze", "--audio", str(audio))

    def test_supported_formats_decode(self) -> None:
        formats = {"track.wav": None, "track.aiff": "AIFF", "track.flac": "FLAC", "track.ogg": "OGG"}
        if "MP3" in analysis.supported_formats():
            formats["track.mp3"] = "MP3"
        for name, format in formats.items():
            with self.subTest(name=name):
                audio = self.dir / name
                write_test_audio(audio, format=format)
                result = analyze_audio(str(audio))
                self.assertAlmostEqual(result.tempo_bpm, 120, delta=1)
                self.assertAlmostEqual(result.duration_seconds, 16, delta=0.1)

    def test_pinned_soundfile_supports_mp3(self) -> None:
        # requirements/build.txt pins a soundfile wheel bundling libsndfile >= 1.1.
        self.assertIn("MP3", sf.available_formats())
        self.assertIn("MP3", analysis.supported_formats())


if __name__ == "__main__":
    unittest.main()
