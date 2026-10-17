"""Updates must never leave users without their previous working OpenBeat installation.

The same scenarios run against the macOS postinstall script (in bash) and the
Windows installer's staged install (in Python). Failures are injected at the
copy and rename steps each installer uses.
"""
import errno
import importlib.util
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from scripts import build_installers, staged_install


ROOT = Path(__file__).resolve().parents[1]
POSTINSTALL = ROOT / "scripts" / "macos_postinstall.sh"
BASH = shutil.which("bash")
SOURCE_MODULE = ROOT / "resolve" / "Fusion" / "Modules" / "OpenBeat" / "OpenBeatCommon.lua"

# Failure injection for the sourced postinstall script: bash functions shadow the commands it runs.
# Each fault fires once, so the rollback can still move the previous installation back, and
# reports itself so a test cannot pass because of some other failure.
BASH_FAULTS = r"""
mv() {
  case "$2" in
    "${FAIL_MOVE_TO:-}") FAIL_MOVE_TO=""; echo "fault: mv" >&2; return 1 ;;
    "${KILL_MOVE_TO:-}") echo "fault: kill" >&2; kill -KILL $$ ;;
    "${TERM_MOVE_TO:-}") TERM_MOVE_TO=""; echo "fault: term" >&2; kill -TERM $$ ;;
  esac
  command mv "$@"
}
cp() {
  local destination="${@: -1}"
  command cp "$@" || return
  case "${COPY_FAULT:-}:$destination" in
    error:*/Scripts/Utility/.OpenBeat.new) echo "fault: cp" >&2; return 1 ;;
    truncate:*/Modules/.OpenBeat.new) echo "fault: cp" >&2; : > "$destination/bin/openbeat" ;;
  esac
}
"""

KILL_DRIVER = """
import os, sys
from pathlib import Path
from scripts import staged_install
rename = os.rename
def killing_rename(source, destination):
    if Path(destination) == Path(sys.argv[3]):
        os._exit(9)
    rename(source, destination)
os.rename = killing_rename
staged_install.install_payload(Path(sys.argv[1]), Path(sys.argv[2]))
"""


def tree(root: Path) -> dict[str, object]:
    """Contents of every file, link, and folder below ``root``."""
    state: dict[str, object] = {}
    for directory, folders, files in os.walk(root):
        for name in folders + files:
            path = Path(directory, name)
            key = path.relative_to(root).as_posix()
            if path.is_symlink():
                state[key] = ("link", os.readlink(path))
            elif path.is_dir():
                state[key] = "folder"
            else:
                state[key] = path.read_bytes()
    return state


def leftovers(root: Path) -> list[str]:
    return sorted(key for key in tree(root) if Path(key).name.startswith(".OpenBeat"))


class UpdateScenarios:
    """Scenarios shared by both installers. Subclasses provide the payload and run the install."""

    platform: str
    runtime: str
    failure = ""  # Output or error from the last failed install, for assertion messages.

    def install(self, payload: Path, root: Path, **faults: str) -> bool:
        raise NotImplementedError

    def setUp(self) -> None:
        temporary = TemporaryDirectory(prefix="openbeat-update-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.root = self.work / "Fusion"
        self.payload = self.work / "payload"
        built = self.work / "build" / "openbeat"
        if self.platform == "windows":
            built.mkdir(parents=True)
            (built / "_internal").mkdir()
            (built / "_internal" / "dependency.dll").write_bytes(b"dependency")
            built = built / "openbeat.exe"
        else:
            built.parent.mkdir(parents=True)
        built.write_bytes(b"new runtime")
        build_installers.build_payload(self.payload, built, self.platform)

    def make_previous_install(self) -> dict[str, object]:
        modules = self.root / "Modules" / "OpenBeat"
        utility = self.root / "Scripts" / "Utility" / "OpenBeat"
        (modules / "bin").mkdir(parents=True)
        utility.mkdir(parents=True)
        (modules / "OpenBeatCommon.lua").write_text("-- previous version\n")
        (modules / "OpenBeatConfig.local.lua").write_text('return { python_bin = "previous" }\n')
        (modules / "bin" / "openbeat").write_bytes(b"previous runtime")
        (utility / "Create Timeline Markers (Quantized).lua").write_text("-- previous version\n")
        (utility / "Removed Action.lua").write_text("-- not in the new version\n")
        (self.root / "Scripts" / "Utility" / "Another Tool.lua").write_text("-- not OpenBeat\n")
        return tree(self.root)

    def damaged_payload(self) -> Path:
        damaged = self.work / "damaged"
        shutil.copytree(self.payload, damaged)
        (damaged / "Scripts" / "Utility" / "OpenBeat" / "Export Subtitles (Quantized).lua").write_text("damaged")
        return damaged

    def assert_new_install(self) -> None:
        modules = self.root / "Modules" / "OpenBeat"
        utility = self.root / "Scripts" / "Utility" / "OpenBeat"
        self.assertEqual((modules / "OpenBeatCommon.lua").read_bytes(), SOURCE_MODULE.read_bytes())
        self.assertTrue((utility / "Create Timeline Markers (Quantized).lua").is_file())
        self.assertFalse((utility / "Removed Action.lua").exists())
        runtime = modules.joinpath(*self.runtime.split("/"))
        self.assertEqual(runtime.read_bytes(), b"new runtime")
        self.assertIn(f'python_bin = "{runtime.as_posix()}"', (modules / "OpenBeatConfig.local.lua").read_text())
        self.assertEqual(leftovers(self.root), [])

    def test_update_replaces_previous_installation(self) -> None:
        self.make_previous_install()
        self.assertTrue(self.install(self.payload, self.root), self.failure)
        self.assert_new_install()
        self.assertEqual((self.root / "Scripts" / "Utility" / "Another Tool.lua").read_text(), "-- not OpenBeat\n")

    def test_fresh_install(self) -> None:
        self.assertTrue(self.install(self.payload, self.root), self.failure)
        self.assert_new_install()

    def test_damaged_payload_keeps_previous_installation(self) -> None:
        before = self.make_previous_install()
        self.assertFalse(self.install(self.damaged_payload(), self.root))
        self.assertEqual(tree(self.root), before)

    def test_failed_copy_keeps_previous_installation(self) -> None:
        before = self.make_previous_install()
        self.assertFalse(self.install(self.payload, self.root, copy="error"))
        self.assertEqual(tree(self.root), before)

    def test_truncated_copy_is_rejected_before_replacing(self) -> None:
        before = self.make_previous_install()
        self.assertFalse(self.install(self.payload, self.root, copy="truncate"))
        self.assertEqual(tree(self.root), before)

    def test_failure_moving_previous_installation_aside_changes_nothing(self) -> None:
        before = self.make_previous_install()
        self.assertFalse(self.install(self.payload, self.root, fail_move_to=self.root / "Modules" / ".OpenBeat.old"))
        self.assertEqual(tree(self.root), before)

    def test_failed_replacement_restores_previous_installation(self) -> None:
        before = self.make_previous_install()
        # Modules has already been replaced when the scripts folder fails to move into place.
        self.assertFalse(self.install(self.payload, self.root, fail_move_to=self.root / "Scripts" / "Utility" / "OpenBeat"))
        self.assertEqual(tree(self.root), before)

    def test_failed_fresh_install_leaves_no_partial_installation(self) -> None:
        self.assertFalse(self.install(self.payload, self.root, fail_move_to=self.root / "Scripts" / "Utility" / "OpenBeat"))
        self.assertFalse((self.root / "Modules" / "OpenBeat").exists())
        self.assertFalse((self.root / "Scripts" / "Utility" / "OpenBeat").exists())
        self.assertEqual(leftovers(self.root), [])

    def test_interrupted_update_is_restored_by_next_run(self) -> None:
        before = self.make_previous_install()
        modules = self.root / "Modules" / "OpenBeat"
        # Killed between moving the installed modules aside and moving the new ones in.
        self.assertFalse(self.install(self.payload, self.root, kill_move_to=modules))
        self.assertFalse(modules.exists())
        self.assertTrue((self.root / "Modules" / ".OpenBeat.old" / "bin" / "openbeat").is_file())

        # Even a run that then fails puts the previous installation back first.
        self.assertFalse(self.install(self.damaged_payload(), self.root))
        self.assertEqual(tree(self.root), before)

        self.assertTrue(self.install(self.payload, self.root), self.failure)
        self.assert_new_install()

    def test_symlinked_development_install_is_replaced_without_touching_checkout(self) -> None:
        checkout = self.work / "checkout" / "OpenBeat"
        checkout.mkdir(parents=True)
        (checkout / "Development Action.lua").write_text("-- checkout\n")
        (self.root / "Scripts" / "Utility").mkdir(parents=True)
        (self.root / "Scripts" / "Utility" / "OpenBeat").symlink_to(checkout, target_is_directory=True)

        self.assertTrue(self.install(self.payload, self.root), self.failure)
        self.assertFalse((self.root / "Scripts" / "Utility" / "OpenBeat").is_symlink())
        self.assertEqual((checkout / "Development Action.lua").read_text(), "-- checkout\n")
        self.assertEqual(leftovers(self.root), [])


@unittest.skipUnless(BASH and shutil.which("shasum"), "bash and shasum are required to run the macOS postinstall script")
class MacOSPostinstallUpdateTests(UpdateScenarios, unittest.TestCase):
    platform = "macos"
    runtime = "bin/openbeat"

    def run_script(self, payload: Path, root: Path, **faults: str) -> subprocess.CompletedProcess[str]:
        environment = {**os.environ, "COPY_FAULT": faults.pop("copy", "")}
        for name, path in faults.items():
            environment[name.upper()] = str(path)
        owner = f"{os.getuid()}:{os.getgid()}"
        command = f'set -u; source "$1"; {BASH_FAULTS}\nopenbeat_install "$2" "$3" "$4"'
        return subprocess.run(
            [BASH, "-c", command, "postinstall", POSTINSTALL, payload, root, owner],
            env=environment,
            text=True,
            capture_output=True,
            timeout=300,
        )

    def install(self, payload: Path, root: Path, **faults: str) -> bool:
        result = self.run_script(payload, root, **faults)
        self.failure = result.stdout + result.stderr
        if faults:
            self.assertIn("fault: ", result.stderr, result.stdout + result.stderr)
        return result.returncode == 0

    def test_termination_during_replacement_restores_previous_installation(self) -> None:
        before = self.make_previous_install()
        result = self.run_script(self.payload, self.root, term_move_to=self.root / "Scripts" / "Utility" / "OpenBeat")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Interrupted; restoring the previous installation", result.stdout)
        self.assertEqual(tree(self.root), before)

    def test_runtime_is_executable(self) -> None:
        self.assertTrue(self.install(self.payload, self.root), self.failure)
        self.assertTrue(os.access(self.root / "Modules" / "OpenBeat" / "bin" / "openbeat", os.X_OK))

    def test_sourcing_the_script_does_not_run_the_installer(self) -> None:
        result = subprocess.run(
            [BASH, "-c", 'source "$1" && type openbeat_install >/dev/null && echo sourced', "test", POSTINSTALL],
            text=True,
            capture_output=True,
            timeout=300,
        )
        self.assertEqual(result.stdout.strip(), "sourced", result.stderr)


class WindowsStagedInstallUpdateTests(UpdateScenarios, unittest.TestCase):
    platform = "windows"
    runtime = "bin/openbeat/openbeat.exe"

    def install(self, payload: Path, root: Path, **faults: str) -> bool:
        if "kill_move_to" in faults:
            result = subprocess.run(
                [sys.executable, "-c", KILL_DRIVER, payload, root, faults["kill_move_to"]],
                cwd=ROOT,
                capture_output=True,
                timeout=300,
            )
            return result.returncode == 0

        copy_fault = faults.get("copy")
        fail_move_to = faults.get("fail_move_to")
        fired = []
        copytree = shutil.copytree
        rename = os.rename

        def faulty_copytree(source: Path, destination: Path, *args: object, **kwargs: object) -> Path:
            # shutil.copytree also calls itself for subfolders; only the staged folders are faulted.
            result = copytree(source, destination, *args, **kwargs)
            staged = Path(destination)
            if staged.name == staged_install.STAGED_NAME:
                if copy_fault == "error" and staged.parent.name == "Utility":
                    fired.append(copy_fault)
                    raise OSError(errno.ENOSPC, "No space left on device", str(staged))
                if copy_fault == "truncate" and staged.parent.name == "Modules":
                    fired.append(copy_fault)
                    staged.joinpath(*self.runtime.split("/")).write_bytes(b"")
            return result

        def faulty_rename(source: Path, destination: Path) -> None:
            nonlocal fail_move_to
            if fail_move_to is not None and Path(destination) == Path(fail_move_to):
                fail_move_to = None
                fired.append("rename")
                raise OSError(errno.EIO, "Simulated rename failure", str(destination))
            rename(source, destination)

        with mock.patch.object(staged_install.shutil, "copytree", faulty_copytree):
            with mock.patch.object(staged_install.os, "rename", faulty_rename):
                try:
                    staged_install.install_payload(payload, root)
                except staged_install.InstallError as exc:
                    self.failure = str(exc)
                    if faults:
                        self.assertTrue(fired, f"Install failed before the injected fault: {exc}")
                    return False
        return True

    def test_error_explains_that_previous_installation_was_kept(self) -> None:
        self.make_previous_install()
        with self.assertRaisesRegex(staged_install.InstallError, "existing OpenBeat installation was not changed"):
            staged_install.install_payload(self.damaged_payload(), self.root)

    def test_rename_retries_while_file_is_briefly_locked(self) -> None:
        self.make_previous_install()
        rename = os.rename
        attempts = []

        def locked_once(source: Path, destination: Path) -> None:
            attempts.append(destination)
            if len(attempts) == 1:
                raise PermissionError(errno.EACCES, "Locked by a scanner", str(destination))
            rename(source, destination)

        with mock.patch.object(staged_install.os, "rename", locked_once), mock.patch.object(staged_install.time, "sleep"):
            staged_install.install_payload(self.payload, self.root)
        self.assertEqual(attempts[0], attempts[1])
        self.assert_new_install()

    @unittest.skipUnless(importlib.util.find_spec("tkinter"), "tkinter is required to import the Windows installer")
    def test_windows_installer_reports_installed_runtime(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        self.addCleanup(sys.path.remove, str(ROOT / "scripts"))
        import windows_installer

        with mock.patch.object(windows_installer, "resolve_payload_root", return_value=self.payload):
            result = windows_installer.install_openbeat(self.root)
        self.assertEqual(result["runtime"], str(self.root / "Modules" / "OpenBeat" / "bin" / "openbeat" / "openbeat.exe"))
        self.assert_new_install()


class ManifestTests(unittest.TestCase):
    def test_manifest_lists_every_payload_file(self) -> None:
        with TemporaryDirectory() as temporary:
            payload = Path(temporary) / "payload"
            runtime = Path(temporary) / "openbeat"
            runtime.write_bytes(b"runtime")
            build_installers.build_payload(payload, runtime, "macos")

            for relative in build_installers.PAYLOAD_DIRS:
                folder = payload / relative
                listed = [line.split("  ", 1)[1] for line in staged_install.manifest_path(folder).read_text().splitlines()]
                files = sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file())
                self.assertEqual(listed, files)
                staged_install.verify_manifest(folder, staged_install.manifest_path(folder))
            self.assertIn("bin/openbeat", staged_install.manifest_path(payload / "Modules" / "OpenBeat").read_text())

    def test_installers_replace_the_folders_the_build_packages(self) -> None:
        self.assertEqual(staged_install.TARGETS, build_installers.PAYLOAD_DIRS)
        self.assertIn(f'OPENBEAT_TARGETS="{" ".join(build_installers.PAYLOAD_DIRS)}"', POSTINSTALL.read_text())

    def test_manifest_rejects_unexpected_paths(self) -> None:
        with TemporaryDirectory() as temporary:
            folder = Path(temporary) / "OpenBeat"
            folder.mkdir()
            manifest = Path(temporary) / "OpenBeat.sha256"
            for line in ("", "not-a-digest  file.lua", f"{'0' * 64}  ../outside.lua", f"{'0' * 64}  /absolute.lua"):
                with self.subTest(line=line):
                    manifest.write_text(line + "\n" if line else "")
                    with self.assertRaises(staged_install.InstallError):
                        staged_install.verify_manifest(folder, manifest)


if __name__ == "__main__":
    unittest.main()
