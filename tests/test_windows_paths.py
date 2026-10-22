"""Non-ASCII paths on Windows, where Resolve's Lua uses the ANSI code page.

These run on any platform: the Windows API and code page are replaced with stand-ins.
"""
import json
import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from openbeat import cli
from scripts import build_installers, staged_install


def lua_bytes(literal: str) -> bytes:
    """Decode a Lua string literal written by ``staged_install.lua_string``."""
    assert literal.startswith('"') and literal.endswith('"') and literal.isascii()
    return re.sub(rb"\\(\d{3})", lambda match: bytes([int(match.group(1))]), literal[1:-1].encode("ascii"))


def config_values(config: str) -> dict[str, bytes]:
    return {key: lua_bytes(value) for key, value in re.findall(r'^  (\w+) = (".*"),$', config, re.MULTILINE)}


class RuntimeConfigTests(unittest.TestCase):
    anchor = Path("C:/Users/José/AppData/Roaming/Blackmagic Design/DaVinci Resolve/Support/Fusion/Modules")
    runtime = anchor / "OpenBeat" / "bin" / "openbeat" / "openbeat.exe"

    def test_ascii_runtime_needs_no_other_spelling(self) -> None:
        runtime = Path("C:/Users/Jo/Fusion/Modules/OpenBeat/bin/openbeat.exe")
        with mock.patch.object(staged_install, "windows_short_path", side_effect=AssertionError):
            config = staged_install.runtime_config(runtime, runtime.parents[2])
        self.assertEqual(config, f'return {{\n  python_bin = "{runtime.as_posix()}",\n}}\n')

    def test_short_path_spells_runtime_in_ascii(self) -> None:
        short = "C:\\Users\\JOS~1\\AppData\\Roaming\\BLACKM~1\\DAVINC~1\\Support\\Fusion\\Modules"
        with mock.patch.object(staged_install, "windows_short_path", return_value=short) as short_path:
            config = staged_install.runtime_config(self.runtime, self.anchor, encoding="cp1252")
        short_path.assert_called_once_with(str(self.anchor))
        self.assertTrue(config.isascii())
        values = config_values(config)
        self.assertEqual(values["python_bin"].decode("utf-8"), self.runtime.as_posix())
        self.assertEqual(
            values["python_bin_ansi"],
            b"C:/Users/JOS~1/AppData/Roaming/BLACKM~1/DAVINC~1/Support/Fusion/Modules/OpenBeat/bin/openbeat/openbeat.exe",
        )

    def test_without_short_names_the_ansi_code_page_is_used(self) -> None:
        # With 8.3 names disabled, GetShortPathNameW returns the long path unchanged.
        for short in (None, str(self.anchor)):
            with self.subTest(short=short), mock.patch.object(staged_install, "windows_short_path", return_value=short):
                values = config_values(staged_install.runtime_config(self.runtime, self.anchor, encoding="cp1252"))
                self.assertEqual(values["python_bin_ansi"], self.runtime.as_posix().encode("cp1252"))
                self.assertIn(b"Jos\xe9", values["python_bin_ansi"])

    def test_unrepresentable_path_falls_back_to_utf8_only(self) -> None:
        anchor = Path("C:/Users/用户/Fusion/Modules")
        with mock.patch.object(staged_install, "windows_short_path", return_value=None):
            config = staged_install.runtime_config(anchor / "OpenBeat" / "bin" / "openbeat.exe", anchor, encoding="cp1252")
        self.assertEqual(set(config_values(config)), {"python_bin"})
        # mbcs only exists on Windows; elsewhere the lookup fails the same way.
        with mock.patch.object(staged_install, "windows_short_path", return_value=None):
            config = staged_install.runtime_config(self.runtime, self.anchor, encoding="no-such-codec")
        self.assertEqual(set(config_values(config)), {"python_bin"})

    def test_short_path_lookup(self) -> None:
        short = staged_install.windows_short_path(str(Path.cwd()))
        if sys.platform == "win32":
            self.assertIsInstance(short, str)
        else:
            self.assertIsNone(short)

    def test_install_records_ansi_runtime_path(self) -> None:
        with TemporaryDirectory(prefix="openbeat-unicode-") as temporary:
            work = Path(temporary)
            built = work / "build" / "openbeat" / "openbeat.exe"
            built.parent.mkdir(parents=True)
            built.write_bytes(b"runtime")
            build_installers.build_payload(work / "payload", built, "windows")
            root = work / "José" / "Fusion"
            short = str(work / "JOS~1" / "Fusion" / "Modules")
            with mock.patch.object(staged_install, "windows_short_path", return_value=short) as short_path:
                runtime = staged_install.install_payload(work / "payload", root)
            short_path.assert_called_once_with(str(root / "Modules"))
            values = config_values((root / "Modules" / "OpenBeat" / staged_install.CONFIG_NAME).read_text(encoding="ascii"))
            self.assertEqual(values["python_bin"].decode("utf-8"), runtime.as_posix())
            relative = runtime.relative_to(root / "Modules").as_posix()
            self.assertEqual(values["python_bin_ansi"].decode("ascii"), Path(short).as_posix() + "/" + relative)


class ArgsFileTests(unittest.TestCase):
    def test_arguments_without_args_file_are_unchanged(self) -> None:
        argv = ["analyze", "--audio", "song.wav"]
        self.assertIs(cli.expand_args_file(argv), argv)

    def test_args_file_arguments_come_first(self) -> None:
        with TemporaryDirectory(prefix="openbeat-args-") as temporary:
            path = Path(temporary) / "args.json"
            # Written by the Resolve scripts: UTF-8, with JSON escapes for backslashes and quotes.
            path.write_bytes('["analyze", "--audio", "C:\\\\Música\\\\canción \\"1\\".wav"]\n'.encode("utf-8"))
            argv = cli.expand_args_file(["--args-file", str(path), "--format", "lua", "--output", "C:\\Temp\\a.lua"])
            args = cli.build_parser().parse_args(argv)
        self.assertEqual(args.command, "analyze")
        self.assertEqual(args.audio, 'C:\\Música\\canción "1".wav')
        self.assertEqual((args.format, args.output), ("lua", "C:\\Temp\\a.lua"))

    def test_args_file_must_list_strings(self) -> None:
        with TemporaryDirectory(prefix="openbeat-args-") as temporary:
            path = Path(temporary) / "args.json"
            for content in ({"audio": "x"}, ["analyze", 1]):
                path.write_text(json.dumps(content), encoding="utf-8")
                with self.subTest(content=content), self.assertRaises(SystemExit):
                    cli.expand_args_file(["--args-file", str(path)])


if __name__ == "__main__":
    unittest.main()
