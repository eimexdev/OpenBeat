import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from scripts import build_installers


class BuildInstallerTests(unittest.TestCase):
    def test_windows_installer_packages_its_source_and_complete_runtime(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / "openbeat"
            runtime.mkdir()
            binary = runtime / "openbeat.exe"
            binary.write_bytes(b"runtime")
            (runtime / "_internal").mkdir()
            (runtime / "_internal" / "dependency.dll").write_bytes(b"dependency")
            installers = root / "installers"
            installers.mkdir()

            def fake_run(cmd: list[str], cwd: Path | None = None) -> None:
                self.assertIsNotNone(cwd)
                entry = cwd / "windows_installer.py"
                self.assertEqual(entry.read_bytes(), (build_installers.ROOT / "scripts" / "windows_installer.py").read_bytes())
                payload = cwd / "payload"
                self.assertEqual((payload / "bin" / "openbeat" / "_internal" / "dependency.dll").read_bytes(), b"dependency")
                for name in ("OpenBeatTiming.lua", "OpenBeatSource.lua", "OpenBeatMarkers.lua", "OpenBeatSubtitles.lua"):
                    self.assertTrue((payload / "Modules" / "OpenBeat" / name).is_file())
                (cwd / "dist").mkdir()
                (cwd / "dist" / "openbeat-installer.exe").write_bytes(b"installer")

            with mock.patch.object(build_installers, "DIST_INSTALLERS", installers):
                with mock.patch.object(build_installers, "run", side_effect=fake_run):
                    result = build_installers.create_windows_exe(binary, "0.0.2")
            self.assertEqual(result.read_bytes(), b"installer")

    def test_windows_cli_runtime_is_onedir_and_windowed(self) -> None:
        with TemporaryDirectory() as tmpdir:
            dist_root = Path(tmpdir) / "dist"

            def fake_run(cmd: list[str], cwd: Path | None = None) -> None:
                runtime = dist_root / "openbeat"
                runtime.mkdir(parents=True)
                (runtime / "openbeat.exe").write_text("")

            with mock.patch.object(build_installers, "DIST_ROOT", dist_root):
                with mock.patch.object(build_installers, "run", side_effect=fake_run) as run:
                    result = build_installers.build_cli_binary(platform="windows", python_bin="py")

        command = run.call_args.args[0]
        self.assertIn("--onedir", command)
        self.assertIn("--windowed", command)
        self.assertNotIn("--onefile", command)
        self.assertEqual(result.name, "openbeat.exe")


if __name__ == "__main__":
    unittest.main()
