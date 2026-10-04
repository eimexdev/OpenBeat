import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openbeat.analysis import BeatAnalysis, to_lua, write_lua_analysis


LUA = shutil.which("lua5.1") or shutil.which("lua") or shutil.which("lua5.4")


class TransportTests(unittest.TestCase):
    @unittest.skipUnless(LUA, "Lua is required to verify serialization")
    def test_lua_round_trip_preserves_unicode_quotes_and_control_characters(self) -> None:
        source_path = 'music 音楽/quote" slash\\\n\r\t\x00é.wav'
        analysis = BeatAnalysis(source_path, 2, 22050, [0.1, 0.6], 120, 0.1, [0.1, 0.6, 1.1, 1.6])
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "analysis.lua"
            write_lua_analysis(analysis, str(path))
            result = subprocess.run(
                [LUA, "-", str(path)], input=b"local data = dofile(arg[1]); io.write(data.audio_path)",
                capture_output=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.decode("utf-8"), source_path)

    def test_nonfinite_numbers_are_rejected(self) -> None:
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                to_lua(value)


if __name__ == "__main__":
    unittest.main()
