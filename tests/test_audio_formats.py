import contextlib
import io
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import numpy as np
import soundfile as sf

from openbeat import analysis, cli
from openbeat.analysis import AudioInputError, analyze_audio, check_audio_source
from scripts.smoke_test_runtime import write_test_audio, write_test_media


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

    def assert_test_beats(self, audio: Path, offset: float = 0.0) -> None:
        result = analyze_audio(str(audio))
        self.assertAlmostEqual(result.tempo_bpm, 120, delta=1)
        self.assertAlmostEqual(result.duration_seconds, 16 + offset, delta=0.1)
        # The clicks are a quarter period apart from the offsets tested, so a lost offset fails.
        period = 60 / result.tempo_bpm
        phase_error = abs((result.grid_offset_seconds - 0.2 - offset + period / 2) % period - period / 2)
        self.assertLess(phase_error, 0.05)

    def test_libsndfile_formats_decode(self) -> None:
        formats = {"track.wav": None, "track.aiff": "AIFF", "track.flac": "FLAC", "track.ogg": "OGG", "track.mp3": "MP3"}
        for name, format in formats.items():
            with self.subTest(name=name):
                audio = self.dir / name
                write_test_audio(audio, format=format)
                self.assert_test_beats(audio)

    def test_ffmpeg_formats_decode(self) -> None:
        sources = {
            "memo.m4a": {},
            "memo.aac.mp4": {},
            "camera.mov": {"audio_codec": "pcm_s16le", "with_video": True},
            "phone.MOV": {"with_video": True},
            "screen.mp4": {"with_video": True},
        }
        for name, options in sources.items():
            with self.subTest(name=name):
                media = self.dir / name
                write_test_media(media, **options)
                self.assert_test_beats(media)

    def test_audio_starting_after_the_video_keeps_its_timeline_position(self) -> None:
        for name, codec in (("late.mov", "pcm_s16le"), ("late.mp4", "aac")):
            with self.subTest(name=name):
                media = self.dir / name
                write_test_media(media, codec, with_video=True, audio_offset=0.25)
                self.assert_test_beats(media, offset=0.25)

    def test_audio_starting_long_after_the_video_keeps_its_position(self) -> None:
        media = self.dir / "long take.mov"
        write_test_media(media, "pcm_s16le", with_video=True, audio_offset=601)
        channels, sr = analysis._read_with_ffmpeg(str(media))
        first_click = np.argmax(np.abs(channels[0]) > 0.05) / sr
        self.assertAlmostEqual(first_click, 601.2, delta=0.01)

    def test_timestamp_gap_is_kept_as_silence(self) -> None:
        for name in ("dropout.mp4", "dropout.mkv"):
            with self.subTest(name=name):
                media = self.dir / name
                write_test_media(media, with_video=True, gap=(8, 9))
                self.assert_test_beats(media)
                beats = analyze_audio(str(media)).raw_beats
                self.assertTrue(any(abs(beat - 12.2) < 0.05 for beat in beats), beats)

    def test_ffmpeg_and_libsndfile_paths_agree(self) -> None:
        wav, m4a = self.dir / "track.wav", self.dir / "track.m4a"
        write_test_audio(wav)
        write_test_media(m4a)
        from_wav, from_m4a = analyze_audio(str(wav)), analyze_audio(str(m4a))
        self.assertAlmostEqual(from_wav.grid_offset_seconds, from_m4a.grid_offset_seconds, delta=0.01)
        self.assertEqual(len(from_wav.raw_beats), len(from_m4a.raw_beats))

    def test_wav_libsndfile_cannot_read_falls_back_to_ffmpeg(self) -> None:
        audio = self.dir / "track.wav"
        write_test_audio(audio)
        with mock.patch.object(analysis, "_read_with_soundfile", side_effect=sf.LibsndfileError(1)):
            self.assert_test_beats(audio)

    def test_unreadable_file_reports_readable_formats(self) -> None:
        clip = self.dir / "interview.m4a"
        clip.write_bytes(b"\0" * 4096)
        code, stderr = run_cli("analyze", "--audio", str(clip), "--output", str(self.dir / "out.json"))

        self.assertEqual(code, 1)
        self.assertIn(f"Can't read audio from {clip}", stderr)
        self.assertIn("damaged", stderr)
        self.assertIn("OpenBeat reads audio files such as WAV", stderr)
        self.assertNotIn("Traceback", stderr)
        self.assertFalse((self.dir / "out.json").exists())

    def test_corrupt_wav_reports_decode_failure(self) -> None:
        corrupt = self.dir / "song.wav"
        corrupt.write_bytes(b"RIFF\0\0\0\0WAVEjunk" * 64)
        code, stderr = run_cli("click-track", "--audio", str(corrupt), "--output", str(self.dir / "c.wav"))

        self.assertEqual(code, 1)
        self.assertIn(f"Can't read audio from {corrupt}", stderr)
        self.assertIn("OpenBeat reads audio files", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_video_without_audio_track_is_reported(self) -> None:
        import av

        silent = self.dir / "b-roll.mp4"
        with av.open(str(silent), "w") as container:
            video = container.add_stream("mpeg4", rate=25)
            video.width, video.height, video.pix_fmt = 64, 64, "yuv420p"
            for index in range(10):
                picture = av.VideoFrame(64, 64, "yuv420p")
                picture.pts = index
                container.mux(video.encode(picture))
            container.mux(video.encode(None))
        with self.assertRaisesRegex(AudioInputError, "has no audio track"):
            analyze_audio(str(silent))

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
        with mock.patch.object(analysis.librosa, "to_mono", side_effect=ValueError("boom")):
            with self.assertRaisesRegex(ValueError, "boom"):
                run_cli("analyze", "--audio", str(audio))

    def test_pinned_soundfile_supports_mp3(self) -> None:
        # requirements/build.txt pins a soundfile wheel bundling libsndfile >= 1.1.
        self.assertIn("MP3", sf.available_formats())


if __name__ == "__main__":
    unittest.main()
