import argparse
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from xml.etree import ElementTree

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

    def build_macos_pkg(self, arches: tuple[str, ...]) -> tuple[list[list[str]], str]:
        """Runs create_macos_pkg with pkgbuild and productbuild stubbed; returns their commands and the distribution."""
        commands: list[list[str]] = []
        distribution: list[str] = []
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtimes = {}
            for arch in arches:
                runtimes[arch] = root / arch / "openbeat"
                runtimes[arch].parent.mkdir()
                runtimes[arch].write_bytes(f"{arch} runtime".encode())
            installers = root / "installers"
            installers.mkdir()

            def fake_run(cmd: list[str], cwd: Path | None = None) -> None:
                commands.append(cmd)
                if cmd[0] == "pkgbuild":
                    self.check_component(cmd, arches)
                    Path(cmd[-1]).write_bytes(b"component")
                else:
                    self.assertEqual(cmd[0], "productbuild")
                    components = Path(cmd[cmd.index("--package-path") + 1])
                    self.assertEqual([path.name for path in components.iterdir()], ["OpenBeat-component.pkg"])
                    distribution.append(Path(cmd[cmd.index("--distribution") + 1]).read_text())
                    Path(cmd[-1]).write_bytes(b"package")

            with mock.patch.object(build_installers, "DIST_INSTALLERS", installers):
                with mock.patch.object(build_installers, "run", side_effect=fake_run):
                    result = build_installers.create_macos_pkg(runtimes, "0.0.2")
            self.assertEqual(result.name, "OpenBeat-macos-0.0.2.pkg")
            self.assertEqual(result.read_bytes(), b"package")
        self.assertEqual([cmd[0] for cmd in commands], ["pkgbuild", "productbuild"])
        return commands, distribution[0]

    def check_component(self, cmd: list[str], arches: tuple[str, ...]) -> None:
        package_root = Path(cmd[cmd.index("--root") + 1])
        scripts = Path(cmd[cmd.index("--scripts") + 1])
        self.assertEqual(cmd[cmd.index("--identifier") + 1], build_installers.MACOS_IDENTIFIER)
        self.assertEqual(cmd[cmd.index("--install-location") + 1], build_installers.MACOS_STAGING)
        self.assertEqual(cmd[cmd.index("--ownership") + 1], "recommended")
        for path in [package_root, *package_root.rglob("*")]:
            self.assertEqual(path.stat().st_mode & 0o022, 0, path)
        postinstall = scripts / "postinstall"
        self.assertEqual(postinstall.read_bytes(), (build_installers.ROOT / "scripts" / "macos_postinstall.sh").read_bytes())
        self.assertTrue(postinstall.stat().st_mode & 0o111)
        self.assertEqual(sorted(path.name for path in (package_root / "payloads").iterdir()), sorted(arches))
        for arch in arches:
            modules = package_root / "payloads" / arch / "Modules" / "OpenBeat"
            self.assertEqual((modules / "bin" / "openbeat").read_bytes(), f"{arch} runtime".encode())
            self.assertEqual((modules / "bin" / "openbeat").stat().st_mode & 0o777, 0o755)
            self.assertFalse((modules / "OpenBeatConfig.local.lua").exists())
            self.assertIn("  bin/openbeat\n", (modules.parent / "OpenBeat.sha256").read_text())
            self.assertIn("LGPL", (modules / "THIRD_PARTY_NOTICES.md").read_text())
            self.assertTrue((modules / "LICENSE").is_file())
            self.assertTrue((package_root / "payloads" / arch / "Scripts" / "Utility" / "OpenBeat.sha256").is_file())

    def test_macos_package_carries_a_runtime_for_each_architecture(self) -> None:
        _, distribution = self.build_macos_pkg(("arm64", "x86_64"))
        document = ElementTree.fromstring(distribution)
        options = document.find("options")
        # Without arm64 here, Apple silicon Macs ask for Rosetta to run the postinstall script.
        self.assertEqual(options.get("hostArchitectures"), "arm64,x86_64")
        self.assertEqual(options.get("customize"), "never")
        self.assertEqual(document.find("domains").get("enable_currentUserHome"), "false")
        self.assertEqual(document.find("volume-check/allowed-os-versions/os-version").get("min"), build_installers.MACOS_MINIMUM)
        self.assertEqual(document.find("choices-outline/line").get("choice"), build_installers.MACOS_IDENTIFIER)
        references = document.findall(".//pkg-ref")
        self.assertEqual({ref.get("id") for ref in references}, {build_installers.MACOS_IDENTIFIER})
        component = next(ref for ref in references if ref.text)
        self.assertEqual((component.text, component.get("version")), ("OpenBeat-component.pkg", "0.0.2"))

    def test_single_architecture_package_only_installs_on_that_architecture(self) -> None:
        _, distribution = self.build_macos_pkg(("x86_64",))
        self.assertEqual(ElementTree.fromstring(distribution).find("options").get("hostArchitectures"), "x86_64")

    def test_macos_package_rejects_unknown_architectures(self) -> None:
        for runtimes in ({}, {"i386": Path("openbeat")}, {"arm64": Path("openbeat"), "ppc": Path("openbeat")}):
            with self.subTest(runtimes=runtimes), self.assertRaises(ValueError):
                build_installers.create_macos_pkg(runtimes, "0.0.2")

    def test_macos_runtime_arguments(self) -> None:
        self.assertEqual(build_installers.parse_macos_runtime("x86_64=dist/x/openbeat"), ("x86_64", Path("dist/x/openbeat")))
        for value in ("dist/openbeat", "universal2=dist/openbeat", "arm64="):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                build_installers.parse_macos_runtime(value)

    def test_postinstall_selects_the_architectures_the_package_carries(self) -> None:
        postinstall = (build_installers.ROOT / "scripts" / "macos_postinstall.sh").read_text()
        self.assertIn('"$staging/payloads/$OPENBEAT_ARCH"', postinstall)
        for arch in build_installers.MACOS_ARCHES:
            self.assertIn(f'OPENBEAT_ARCH="{arch}"', postinstall)

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
