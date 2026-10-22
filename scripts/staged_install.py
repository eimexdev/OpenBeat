"""Replace an OpenBeat installation without losing the working copy on failure.

The Windows installer uses this module; ``macos_postinstall.sh`` performs the
same steps in bash. For each payload folder, relative to the Resolve Fusion
support folder:

1. Restore any installation that an interrupted earlier update left aside.
2. Copy the payload folder next to its target as ``.OpenBeat.new`` and verify
   it against the SHA-256 manifest written by ``build_installers.py``.
3. Rename the current target to ``.OpenBeat.old`` and the staged folder to the
   target name. Both renames stay inside one folder, so each is atomic.
4. If anything fails, rename ``.OpenBeat.old`` back into place. Once every
   target is replaced, discard the ``.OpenBeat.old`` folders.

A ``.OpenBeat.old`` folder left behind by a crash or power loss is restored by
the next run before it stages anything. Installers running at the same time
would share those folder names, so ``install_payload`` holds a lock throughout.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Iterator

# Modules goes first: if Resolve still holds the runtime open, the update stops
# before anything has changed.
TARGETS = ("Modules/OpenBeat", "Scripts/Utility/OpenBeat")
STAGED_NAME = ".OpenBeat.new"
PREVIOUS_NAME = ".OpenBeat.old"
DISCARD_NAME = ".OpenBeat.discard"
# Written next to the first target once every target is replaced. While it exists the
# update counts as complete, so leftover previous folders are deleted, never restored.
COMMITTED_NAME = ".OpenBeat.committed"
CONFIG_NAME = "OpenBeatConfig.local.lua"

_DIGEST = re.compile(r"[0-9a-f]{64}")


class InstallError(RuntimeError):
    pass


def runtime_executable(modules: Path) -> Path:
    """Return the bundled runtime inside a ``Modules/OpenBeat`` folder."""
    onedir_exe = modules / "bin" / "openbeat" / "openbeat.exe"
    if onedir_exe.exists():
        return onedir_exe
    return modules / "bin" / "openbeat.exe"


def windows_short_path(path: str) -> str | None:
    """Return the 8.3 short form of an existing ``path``, or ``None`` where unavailable."""
    try:
        import ctypes
        from ctypes import wintypes

        get_short_path = ctypes.windll.kernel32.GetShortPathNameW
    except Exception:
        return None
    get_short_path.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    get_short_path.restype = wintypes.DWORD
    size = get_short_path(path, None, 0)
    if not size:
        return None
    buffer = ctypes.create_unicode_buffer(size)
    if not 0 < get_short_path(path, buffer, size) < size:
        return None
    return buffer.value


def ansi_path(path: Path, anchor: Path, encoding: str = "mbcs") -> bytes | None:
    """Spell a non-ASCII ``path`` for Lua 5.1 on Windows, or return ``None`` if it cannot.

    Resolve's Lua opens files and starts processes through the ANSI code page, so the
    UTF-8 path never matches. The 8.3 short path is plain ASCII where the volume has
    short names; otherwise the path encoded in the ANSI code page works if each of its
    characters exists there. ``path`` need not exist yet: it is spelled as the short
    form of the existing folder ``anchor`` followed by the rest of ``path``.
    """
    text = path.as_posix()
    if text.isascii():
        return None
    rest = path.relative_to(anchor).parts
    short = windows_short_path(str(anchor))
    if short and short.isascii() and all(name.isascii() for name in rest):
        return "/".join([short.replace("\\", "/").rstrip("/"), *rest]).encode("ascii")
    try:
        return text.encode(encoding)
    except (UnicodeError, LookupError):
        return None


def lua_string(value: bytes) -> str:
    """Quote ``value`` as a Lua string literal made of ASCII characters only."""
    return '"' + "".join(
        chr(byte) if 32 <= byte < 127 and byte not in (34, 92) else f"\\{byte:03d}" for byte in value
    ) + '"'


def runtime_config(runtime: Path, anchor: Path, encoding: str = "mbcs") -> str:
    """The ``OpenBeatConfig.local.lua`` that points the Resolve scripts at ``runtime``."""
    lines = [f"  python_bin = {lua_string(runtime.as_posix().encode('utf-8'))},"]
    ansi = ansi_path(runtime, anchor, encoding)
    if ansi is not None:
        lines.append(f"  python_bin_ansi = {lua_string(ansi)},")
    return "return {\n" + "\n".join(lines) + "\n}\n"


def manifest_path(directory: Path) -> Path:
    return directory.with_name(f"{directory.name}.sha256")


def verify_manifest(directory: Path, manifest: Path) -> None:
    """Check that ``directory`` holds every file listed in ``manifest`` with the recorded digest."""
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise InstallError(f"The installer payload manifest {manifest} is unreadable: {exc}.") from exc
    if not lines:
        raise InstallError(f"The installer payload manifest {manifest} is empty.")
    for line in lines:
        digest, _, name = line.partition("  ")
        relative = PurePosixPath(name)
        if not name or not _DIGEST.fullmatch(digest) or relative.is_absolute() or ".." in relative.parts:
            raise InstallError(f"The installer payload manifest {manifest} is malformed: {line!r}.")
        path = directory.joinpath(*relative.parts)
        if not path.is_file():
            raise InstallError(f"{path} is missing from the prepared installation.")
        with path.open("rb") as handle:
            if hashlib.file_digest(handle, "sha256").hexdigest() != digest:
                raise InstallError(f"{path} does not match the installer payload.")


def _exists(path: Path) -> bool:
    return os.path.lexists(path)


def _remove(path: Path) -> None:
    if os.path.islink(path) or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _discard(path: Path) -> None:
    try:
        _remove(path)
    except OSError:
        pass


def _rename(source: Path, destination: Path, attempts: int = 5) -> None:
    if _exists(destination):
        raise FileExistsError(f"{destination} already exists")
    for attempt in range(1, attempts + 1):
        try:
            os.rename(source, destination)
            return
        except PermissionError:
            # Antivirus and indexing services briefly hold newly written files open on Windows.
            if attempt == attempts:
                raise
            time.sleep(0.2 * attempt)


def _targets(resolve_root: Path) -> list[Path]:
    return [resolve_root.joinpath(*PurePosixPath(target).parts) for target in TARGETS]


def _restore(targets: list[Path], created: tuple[Path, ...] = ()) -> None:
    """Put each ``.OpenBeat.old`` folder back and remove staged copies.

    ``created`` lists targets that did not exist before this run; they are removed.
    """
    failures = []
    for target in targets:
        staged = target.with_name(STAGED_NAME)
        previous = target.with_name(PREVIOUS_NAME)
        discard = target.with_name(DISCARD_NAME)
        try:
            _remove(staged)
            _remove(discard)
            if _exists(previous):
                if _exists(target):
                    _rename(target, discard)
                _rename(previous, target)
            elif target in created:
                _remove(target)
        except OSError as exc:
            failures.append(f"{target}: {exc}")
        _discard(discard)
    if failures:
        raise OSError("; ".join(failures))


def _committed_marker(targets: list[Path]) -> Path:
    return targets[0].with_name(COMMITTED_NAME)


def _finish(targets: list[Path]) -> None:
    """Delete what a committed update left behind, then its marker."""
    failures = []
    for target in targets:
        for name in (PREVIOUS_NAME, DISCARD_NAME, STAGED_NAME):
            try:
                _remove(target.with_name(name))
            except OSError as exc:
                failures.append(f"{target.with_name(name)}: {exc}")
    if failures:
        # Keep the marker, so the next run deletes these instead of restoring them.
        raise OSError("; ".join(failures))
    _committed_marker(targets).unlink(missing_ok=True)


def restore_interrupted_update(resolve_root: Path) -> None:
    """Complete or undo an update that stopped early, so both targets match again."""
    targets = _targets(resolve_root)
    try:
        if _exists(_committed_marker(targets)):
            _finish(targets)
        else:
            _restore(targets)
    except OSError as exc:
        raise InstallError(
            "A previous OpenBeat update was interrupted and could not be undone automatically. "
            f"Close DaVinci Resolve and run the installer again. Details: {exc}"
        ) from exc


def _stage(payload_root: Path, targets: list[Path]) -> Path:
    for relative, target in zip(TARGETS, targets):
        source = payload_root.joinpath(*PurePosixPath(relative).parts)
        staged = target.with_name(STAGED_NAME)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, staged, symlinks=True)
        verify_manifest(staged, manifest_path(source))

    modules = targets[0]
    staged_modules = modules.with_name(STAGED_NAME)
    staged_runtime = runtime_executable(staged_modules)
    if not staged_runtime.is_file():
        raise InstallError("The installer payload does not contain the OpenBeat runtime.")
    runtime = modules / staged_runtime.relative_to(staged_modules)
    config = runtime_config(runtime, anchor=modules.parent)
    (staged_modules / CONFIG_NAME).write_text(config, encoding="ascii")
    return runtime


def lock_path() -> Path:
    return Path(tempfile.gettempdir()) / "OpenBeat-installer.lock"


@contextmanager
def _single_installer() -> Iterator[None]:
    """Hold an OS file lock, which is released even if the installer crashes."""
    path = lock_path()
    with open(path, "a+b") as handle:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise InstallError(
                "Another OpenBeat installer is already running. Let it finish, then run this one again if needed."
            ) from exc
        yield


def install_payload(payload_root: Path, resolve_root: Path) -> Path:
    """Install ``payload_root`` into ``resolve_root`` and return the installed runtime.

    Raises ``InstallError`` after restoring the previous installation if anything fails.
    """
    with _single_installer():
        return _install_payload(payload_root, resolve_root)


def _install_payload(payload_root: Path, resolve_root: Path) -> Path:
    restore_interrupted_update(resolve_root)
    targets = _targets(resolve_root)

    try:
        runtime = _stage(payload_root, targets)
    except BaseException as exc:
        for target in targets:
            _discard(target.with_name(STAGED_NAME))
        if isinstance(exc, InstallError):
            raise InstallError(f"{exc} Your existing OpenBeat installation was not changed.") from exc
        if isinstance(exc, Exception):
            raise InstallError(
                f"Could not prepare the new OpenBeat files: {exc}. Your existing OpenBeat installation was not changed."
            ) from exc
        raise

    created: list[Path] = []
    try:
        for target in targets:
            if _exists(target):
                _rename(target, target.with_name(PREVIOUS_NAME))
            else:
                created.append(target)
            _rename(target.with_name(STAGED_NAME), target)
        _committed_marker(targets).write_bytes(b"")
    except BaseException as exc:
        try:
            _restore(targets, tuple(created))
        except OSError as restore_exc:
            raise InstallError(
                f"Could not replace OpenBeat ({exc}) or restore the previous installation ({restore_exc}). "
                "Close DaVinci Resolve and run the installer again to restore it."
            ) from exc
        if isinstance(exc, Exception):
            raise InstallError(
                f"Could not replace OpenBeat: {exc}. The previous OpenBeat installation was restored; "
                "close DaVinci Resolve and try again."
            ) from exc
        raise

    # Every target is replaced and the marker records it. A folder that cannot be deleted
    # now, for example one Resolve holds open, is deleted by the next run.
    try:
        _finish(targets)
    except OSError:
        pass
    return runtime
