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
                for name in ("windows_installer.py", "staged_install.py"):
                    self.assertEqual((cwd / name).read_bytes(), (build_installers.ROOT / "scripts" / name).read_bytes())
                modules = cwd / "payload" / "Modules" / "OpenBeat"
                self.assertEqual((modules / "bin" / "openbeat" / "_internal" / "dependency.dll").read_bytes(), b"dependency")
                for name in ("OpenBeatTiming.lua", "OpenBeatSource.lua", "OpenBeatMarkers.lua", "OpenBeatSubtitles.lua"):
                    self.assertTrue((modules / name).is_file())
                self.assertIn("bin/openbeat/_internal/dependency.dll", (modules.parent / "OpenBeat.sha256").read_text())
                self.assertTrue((cwd / "payload" / "Scripts" / "Utility" / "OpenBeat.sha256").is_file())
                (cwd / "dist").mkdir()
                (cwd / "dist" / "openbeat-installer.exe").write_bytes(b"installer")

            with mock.patch.object(build_installers, "DIST_INSTALLERS", installers):
                with mock.patch.object(build_installers, "run", side_effect=fake_run):
                    result = build_installers.create_windows_exe(binary, "0.0.2")
            self.assertEqual(result.read_bytes(), b"installer")

    def test_macos_package_runs_the_staged_postinstall_script(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "openbeat"
            binary.write_bytes(b"runtime")
            installers = root / "installers"
            installers.mkdir()

            def fake_pkgbuild(cmd: list[str], cwd: Path | None = None) -> None:
                package_root = Path(cmd[cmd.index("--root") + 1])
                scripts = Path(cmd[cmd.index("--scripts") + 1])
                self.assertEqual(cmd[cmd.index("--install-location") + 1], build_installers.MACOS_STAGING)
                self.assertEqual(cmd[cmd.index("--ownership") + 1], "recommended")
                for path in [package_root, *package_root.rglob("*")]:
                    self.assertEqual(path.stat().st_mode & 0o022, 0, path)
                self.assertEqual((package_root / "payload" / "Modules" / "OpenBeat" / "bin" / "openbeat").stat().st_mode & 0o777, 0o755)
                postinstall = scripts / "postinstall"
                self.assertEqual(postinstall.read_bytes(), (build_installers.ROOT / "scripts" / "macos_postinstall.sh").read_bytes())
                self.assertTrue(postinstall.stat().st_mode & 0o111)
                modules = package_root / "payload" / "Modules" / "OpenBeat"
                self.assertEqual((modules / "bin" / "openbeat").read_bytes(), b"runtime")
                self.assertFalse((modules / "OpenBeatConfig.local.lua").exists())
                self.assertIn("  bin/openbeat\n", (modules.parent / "OpenBeat.sha256").read_text())
                self.assertTrue((package_root / "payload" / "Scripts" / "Utility" / "OpenBeat.sha256").is_file())
                Path(cmd[-1]).write_bytes(b"package")

            with mock.patch.object(build_installers, "DIST_INSTALLERS", installers):
                with mock.patch.object(build_installers, "run", side_effect=fake_pkgbuild):
                    result = build_installers.create_macos_pkg(binary, "0.0.2")
            self.assertEqual(result.read_bytes(), b"package")

    def test_macos_package_stages_where_the_postinstall_script_checks(self) -> None:
        self.assertTrue(build_installers.MACOS_STAGING.startswith("/Library/"))
        postinstall = (build_installers.ROOT / "scripts" / "macos_postinstall.sh").read_text()
        self.assertIn(f'OPENBEAT_STAGING="{build_installers.MACOS_STAGING.lstrip("/")}"', postinstall)
        self.assertNotIn("/tmp", postinstall)

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
