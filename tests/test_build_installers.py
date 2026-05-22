import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from scripts import build_installers


class BuildInstallerTests(unittest.TestCase):
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
