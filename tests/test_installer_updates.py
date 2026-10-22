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

try:
    import pwd
except ImportError:  # Windows; the macOS postinstall tests are skipped there.
    pwd = None


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

HOLD_LOCK_DRIVER = """
import time
from scripts import staged_install
with staged_install._single_installer():
    print("locked", flush=True)
    time.sleep(300)
"""

# Stand-ins for the macOS commands openbeat_main uses to find the user and inspect the staging folder.
BASH_MACOS = r"""
stat() {
  if [ "$1" = "-f" ] && [ "$2" = "%Su" ]; then
    [ -n "${CONSOLE_USER:-}" ] && printf '%s\n' "$CONSOLE_USER"
  elif [ "$1" = "-f" ] && [ "$2" = "%u %Lp" ]; then
    command stat -c '%u %a' "$3"
  else
    command stat "$@"
  fi
}
dscl() {
  if [ -n "${FAKE_DSCL_WRAPPED:-}" ]; then
    printf 'NFSHomeDirectory:\n %s\n' "$FAKE_HOME"
  else
    printf 'NFSHomeDirectory: %s\n' "$FAKE_HOME"
  fi
}
openbeat_as_user() { echo "as user $1" >&2; shift; "$@"; }
openbeat_acl_entries() {
  echo " 0: group:everyone deny delete"
  case "|${FAKE_ACL_WRITABLE:-}|" in
    *"|$1|"*) echo " 1: user:mallory allow add_file,add_subdirectory,delete_child" ;;
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

    def test_interrupted_cleanup_after_replacement_completes_the_update(self) -> None:
        self.make_previous_install()
        self.assertTrue(self.install(self.payload, self.root), self.failure)
        installed = tree(self.root)
        # Interrupted after both targets were replaced and the previous modules deleted,
        # but before the previous scripts folder was deleted.
        previous_scripts = self.root / "Scripts" / "Utility" / ".OpenBeat.old"
        previous_scripts.mkdir()
        (previous_scripts / "Create Timeline Markers (Quantized).lua").write_text("-- previous version\n")
        (self.root / "Modules" / ".OpenBeat.committed").write_bytes(b"")

        # The next run finishes the update rather than restoring only the scripts,
        # even when it then fails itself.
        self.assertFalse(self.install(self.damaged_payload(), self.root))
        self.assertEqual(tree(self.root), installed)

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
        command = f'set -u; source "$1"; {BASH_FAULTS}\nopenbeat_install "$2" "$3"'
        return subprocess.run(
            [BASH, "-c", command, "postinstall", POSTINSTALL, payload, root],
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

    def test_files_left_in_the_staging_folder_by_an_older_package_are_refused(self) -> None:
        before = self.make_previous_install()
        stale = self.work / "stale"
        shutil.copytree(self.payload, stale)
        (stale / "Scripts" / "Utility" / "OpenBeat" / "Removed Action.lua").write_text("-- old package\n")
        result = self.run_script(stale, self.root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("include files the installer payload does not list", result.stdout)
        self.assertEqual(tree(self.root), before)

    def test_resolve_folder_the_user_cannot_write_stops_with_the_fix(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("root can write to any folder")
        before = self.make_previous_install()
        modules, utility = self.root / "Modules", self.root / "Scripts" / "Utility"
        for folder in (modules, utility):
            folder.chmod(0o555)
            self.addCleanup(folder.chmod, 0o755)
        result = self.run_script(self.payload, self.root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        # One command fixes every folder, so a single extra run is enough.
        user = pwd.getpwuid(os.getuid()).pw_name
        self.assertEqual(self.suggested_chown(result.stdout), [user, str(modules), str(utility)])
        for folder in (modules, utility):
            folder.chmod(0o755)
        self.assertEqual(tree(self.root), before)

    def test_suggested_chown_command_survives_shell_characters_in_paths(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("root can write to any folder")
        root = self.work / "it's \"odd\" $HOME `id`" / "Fusion"
        (root / "Modules").mkdir(parents=True)
        (root / "Modules").chmod(0o555)
        self.addCleanup((root / "Modules").chmod, 0o755)
        result = self.run_script(self.payload, root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(self.suggested_chown(result.stdout)[1:], [str(root / "Modules")])

    def suggested_chown(self, output: str) -> list[str]:
        """The arguments the logged sudo command passes to chown, as a shell would parse them."""
        command = output.split("In Terminal, run: ", 1)[1].split(" and then run this installer again.", 1)[0]
        self.assertTrue(command.startswith("sudo chown "), command)
        parsed = subprocess.run(
            [BASH, "-c", 'sudo() { shift; printf "%s\\0" "$@"; }\n' + command],
            capture_output=True,
            text=True,
            check=True,
        )
        return parsed.stdout.split("\0")[:-1]

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


@unittest.skipUnless(BASH and shutil.which("shasum"), "bash and shasum are required to run the macOS postinstall script")
@unittest.skipUnless(pwd is not None and os.getuid() >= 500, "needs a POSIX user account that is not a system account")
class MacOSPostinstallMainTests(unittest.TestCase):
    """The package entry point: where it takes the payload from and whom it installs for."""

    def setUp(self) -> None:
        temporary = TemporaryDirectory(prefix="openbeat-postinstall-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.user = pwd.getpwuid(os.getuid()).pw_name
        self.home = self.work / "home"
        self.home.mkdir()
        self.volume = self.work / "volume"
        self.staging = self.volume.joinpath(*build_installers.MACOS_STAGING.strip("/").split("/"))
        runtime = self.work / "openbeat"
        runtime.write_bytes(b"new runtime")
        build_installers.build_payload(self.staging / "payload", runtime, "macos")
        path = self.staging
        while path != self.volume:
            path.chmod(0o755)
            path = path.parent
        self.volume.chmod(0o755)

    def run_main(self, trusted_uid: int | None = None, **environment: str) -> subprocess.CompletedProcess[str]:
        env = {key: value for key, value in os.environ.items() if key not in ("USER", "SUDO_USER")}
        env.update({"CONSOLE_USER": self.user, "FAKE_HOME": str(self.home)}, **environment)
        uid = os.getuid() if trusted_uid is None else trusted_uid
        command = f'set -u; source "$1"; {BASH_MACOS}\nOPENBEAT_TRUSTED_UID={uid}\nopenbeat_main "$2/OpenBeat.pkg" "$3" "$2"'
        return subprocess.run(
            [BASH, "-c", command, "postinstall", POSTINSTALL, self.volume, build_installers.MACOS_STAGING],
            env=env,
            text=True,
            capture_output=True,
            timeout=300,
        )

    @property
    def modules(self) -> Path:
        return self.home / "Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Modules/OpenBeat"

    def assert_refused(self, result: subprocess.CompletedProcess[str], message: str) -> None:
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(message, result.stdout)
        self.assertNotIn("unbound variable", result.stderr)
        self.assertFalse((self.home / "Library").exists())

    def test_installs_for_console_user_and_removes_staged_payload(self) -> None:
        result = self.run_main()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.modules / "bin" / "openbeat").read_bytes(), b"new runtime")
        self.assertIn(f"as user {self.user}", result.stderr)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.staging.parent.exists())
        self.assertTrue(self.staging.parent.parent.is_dir())

    def test_files_in_the_users_folder_are_only_touched_as_the_user(self) -> None:
        # Root may only check the staging folder and pick the user; openbeat_install runs
        # in the shell started as that user, which has no access to root's functions.
        result = self.run_main()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        script = POSTINSTALL.read_text()
        main = script[script.index("openbeat_main() {"):]
        self.assertNotIn("openbeat_install ", main)
        self.assertNotRegex(main, r"\b(chmod|chown|cp|mv)\b")

    def test_home_folder_with_spaces_and_quotes(self) -> None:
        for wrapped in ("", "1"):
            with self.subTest(wrapped=bool(wrapped)):
                home = self.work / f'User Homes{wrapped}' / 'al "ice"\\x'
                home.mkdir(parents=True)
                self.home = home
                if wrapped:
                    self.setUp()
                    self.home = home
                result = self.run_main(FAKE_HOME=str(home), FAKE_DSCL_WRAPPED=wrapped)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                config = (self.modules / "OpenBeatConfig.local.lua").read_text()
                runtime = str(self.modules / "bin" / "openbeat")
                self.assertIn(runtime.replace("\\", "\\\\").replace('"', '\\"'), config)
                if shutil.which("lua5.1"):
                    # The config must load in Lua and give back the exact path.
                    check = self.work / "check_config.lua"
                    check.write_text(
                        f"local c = dofile({str(self.modules / 'OpenBeatConfig.local.lua')!r})\n"
                        f"assert(c.python_bin == {runtime!r}, c.python_bin)\n"
                    )
                    lua = subprocess.run(["lua5.1", str(check)], text=True, capture_output=True)
                    self.assertEqual(lua.returncode, 0, lua.stdout + lua.stderr)

    def test_command_line_install_with_nobody_logged_in_uses_sudo_user(self) -> None:
        result = self.run_main(CONSOLE_USER="root", SUDO_USER=self.user)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.modules / "bin" / "openbeat").is_file())

    def test_unknown_user_fails_clearly_without_installing_for_root(self) -> None:
        for console_user in ("root", "loginwindow", ""):
            with self.subTest(console_user=console_user):
                self.setUp()
                result = self.run_main(CONSOLE_USER=console_user)
                self.assert_refused(result, "Could not tell which user to install OpenBeat for")
                self.assertFalse(self.staging.exists())

    def test_system_account_is_not_an_install_target(self) -> None:
        system_user = next((entry.pw_name for entry in pwd.getpwall() if 0 < entry.pw_uid < 500), None)
        if system_user is None:
            self.skipTest("no system account to test with")
        result = self.run_main(CONSOLE_USER="root", SUDO_USER=system_user)
        self.assert_refused(result, "Could not tell which user to install OpenBeat for")

    def test_refuses_staging_folders_other_users_can_write(self) -> None:
        for folder, mode in ((self.staging, 0o775), (self.staging, 0o757), (self.volume / "Library", 0o777)):
            with self.subTest(folder=folder, mode=oct(mode)):
                folder.chmod(mode)
                result = self.run_main()
                folder.chmod(0o755)
                self.assert_refused(result, f"Refusing to install: {folder} must belong to root")
                # The payload is left alone rather than deleted as root.
                self.assertTrue((self.staging / "payload").is_dir())

    def test_refuses_volume_root_other_users_can_write(self) -> None:
        self.volume.chmod(0o777)
        self.addCleanup(self.volume.chmod, 0o755)
        self.assert_refused(self.run_main(), f"Refusing to install: {self.volume} must belong to root")
        # The payload is left alone rather than deleted as root.
        self.assertTrue(self.staging.is_dir())

    def test_refuses_folders_an_access_control_entry_lets_others_change(self) -> None:
        for folder in (self.volume, self.staging.parent):
            with self.subTest(folder=folder):
                result = self.run_main(FAKE_ACL_WRITABLE=str(folder))
                self.assert_refused(result, f"an access control entry lets other users change {folder}")
                self.assertTrue(self.staging.is_dir())

    def test_refuses_staging_owned_by_another_user(self) -> None:
        result = self.run_main(trusted_uid=0)
        self.assert_refused(result, "must belong to root and be writable only by root")
        self.assertTrue(self.staging.is_dir())

    def test_refuses_symlinked_staging_folder(self) -> None:
        elsewhere = self.work / "elsewhere"
        self.staging.rename(elsewhere)
        self.staging.symlink_to(elsewhere, target_is_directory=True)
        result = self.run_main()
        self.assert_refused(result, f"Refusing to install: {self.staging} is not a folder")
        self.assertTrue((elsewhere / "payload").is_dir())

    def test_refuses_missing_staging_folder(self) -> None:
        shutil.rmtree(self.staging)
        self.assert_refused(self.run_main(), "is not a folder")


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

    def test_second_installer_waits_for_the_first(self) -> None:
        before = self.make_previous_install()
        # Holds the lock the way a running installer does, from another process.
        holder = subprocess.Popen(
            [sys.executable, "-c", HOLD_LOCK_DRIVER],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(holder.wait)
        self.addCleanup(holder.kill)
        self.assertEqual(holder.stdout.readline().strip(), "locked")

        self.assertFalse(self.install(self.payload, self.root))
        self.assertIn("Another OpenBeat installer is already running", self.failure)
        self.assertEqual(tree(self.root), before)

        holder.kill()
        holder.wait()
        self.assertTrue(self.install(self.payload, self.root), self.failure)
        self.assert_new_install()

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
