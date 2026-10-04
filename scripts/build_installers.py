from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = ROOT / "dist"
DIST_INSTALLERS = DIST_ROOT / "installers"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, check=True, cwd=cwd or ROOT)


def clean() -> None:
    DIST_INSTALLERS.mkdir(parents=True, exist_ok=True)


def parse_version() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text()
    for line in pyproject.splitlines():
        if line.strip().startswith("version ="):
            return line.split("=", 1)[1].strip().strip('"')
    raise ValueError("Unable to find version in pyproject.toml")


def pyinstaller_binary(
    output_name: str,
    entry_script: Path,
    python_bin: str = "python",
    *,
    onefile: bool = True,
    windowed: bool = False,
) -> Path:
    for stale_output in (DIST_ROOT / output_name, DIST_ROOT / f"{output_name}.exe"):
        if stale_output.is_dir():
            shutil.rmtree(stale_output)
        elif stale_output.exists():
            stale_output.unlink()

    cmd = [
        python_bin,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--name",
        output_name,
        "--specpath",
        str(ROOT / "build"),
    ]
    cmd.append("--onefile" if onefile else "--onedir")
    if windowed:
        cmd.append("--windowed")
    cmd.append(str(entry_script))
    run(cmd)

    if onefile:
        candidates = [DIST_ROOT / output_name, DIST_ROOT / f"{output_name}.exe"]
    else:
        candidates = [
            DIST_ROOT / output_name / output_name,
            DIST_ROOT / output_name / f"{output_name}.exe",
        ]
    built = next((path for path in candidates if path.exists()), None)
    if built is None:
        raise FileNotFoundError(f"Expected bundled binary at one of: {candidates}")
    return built


def build_cli_binary(platform: str, python_bin: str = "python") -> Path:
    return pyinstaller_binary(
        "openbeat",
        ROOT / "openbeat" / "cli.py",
        python_bin=python_bin,
        onefile=platform != "windows",
        windowed=platform == "windows",
    )


def copy_payload(payload_root: Path) -> None:
    shutil.copytree(
        ROOT / "resolve" / "Fusion" / "Scripts" / "Utility" / "OpenBeat",
        payload_root / "Utility" / "OpenBeat",
        dirs_exist_ok=True,
    )
    shutil.copytree(
        ROOT / "resolve" / "Fusion" / "Modules" / "OpenBeat",
        payload_root / "Modules" / "OpenBeat",
        dirs_exist_ok=True,
    )


def create_macos_pkg(cli_binary: Path, version: str) -> Path:
    with tempfile.TemporaryDirectory(prefix="openbeat-macos-installer-") as tmp:
        tmp_path = Path(tmp)
        root_dir = tmp_path / "root"
        payload_dir = root_dir / "payload"
        copy_payload(payload_dir)

        bin_dir = payload_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cli_binary, bin_dir / "openbeat")
        (bin_dir / "openbeat").chmod(0o755)

        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        postinstall = scripts_dir / "postinstall"
        postinstall.write_text(
            """#!/usr/bin/env bash
set -euo pipefail

PAYLOAD_ROOT="$3/private/tmp/OpenBeatInstaller/payload"
CONSOLE_USER="$(stat -f %Su /dev/console)"
if [[ -z "${CONSOLE_USER}" || "${CONSOLE_USER}" == "root" ]]; then
  CONSOLE_USER="${SUDO_USER:-$USER}"
fi
USER_HOME="$(dscl . -read /Users/"${CONSOLE_USER}" NFSHomeDirectory | awk '{print $2}')"

RESOLVE_ROOT="$USER_HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion"
UTILITY_TARGET="$RESOLVE_ROOT/Scripts/Utility/OpenBeat"
MODULE_TARGET="$RESOLVE_ROOT/Modules/OpenBeat"

mkdir -p "$RESOLVE_ROOT/Scripts/Utility" "$RESOLVE_ROOT/Modules"
rm -rf "$UTILITY_TARGET" "$MODULE_TARGET"
cp -R "$PAYLOAD_ROOT/Utility/OpenBeat" "$UTILITY_TARGET"
cp -R "$PAYLOAD_ROOT/Modules/OpenBeat" "$MODULE_TARGET"
mkdir -p "$MODULE_TARGET/bin"
cp "$PAYLOAD_ROOT/bin/openbeat" "$MODULE_TARGET/bin/openbeat"
chmod +x "$MODULE_TARGET/bin/openbeat"

cat > "$MODULE_TARGET/OpenBeatConfig.local.lua" <<EOF
return {
  python_bin = "$MODULE_TARGET/bin/openbeat",
}
EOF

chown -R "$CONSOLE_USER":staff "$UTILITY_TARGET" "$MODULE_TARGET"
rm -rf "$3/private/tmp/OpenBeatInstaller"
exit 0
"""
        )
        postinstall.chmod(0o755)

        pkg_path = DIST_INSTALLERS / f"OpenBeat-macos-{version}.pkg"
        run(
            [
                "pkgbuild",
                "--identifier",
                "org.openbeat.installer",
                "--version",
                version,
                "--root",
                str(root_dir),
                "--scripts",
                str(scripts_dir),
                "--install-location",
                "/private/tmp/OpenBeatInstaller",
                str(pkg_path),
            ]
        )
        return pkg_path


def create_windows_exe(cli_binary: Path, version: str, python_bin: str = "python") -> Path:
    output_exe = DIST_INSTALLERS / f"OpenBeat-windows-{version}-installer.exe"
    with tempfile.TemporaryDirectory(prefix="openbeat-win-installer-") as tmp:
        tmp_path = Path(tmp)
        payload_dir = tmp_path / "payload"
        copy_payload(payload_dir)
        payload_bin_dir = payload_dir / "bin"
        payload_bin_dir.mkdir(parents=True, exist_ok=True)
        if cli_binary.parent.name == "openbeat":
            shutil.copytree(cli_binary.parent, payload_bin_dir / "openbeat", dirs_exist_ok=True)
        else:
            shutil.copy2(cli_binary, payload_bin_dir / "openbeat.exe")

        installer_entry = tmp_path / "windows_installer.py"
        shutil.copy2(ROOT / "scripts" / "windows_installer.py", installer_entry)

        run(
            [
                python_bin,
                "-m",
                "PyInstaller",
                "--clean",
                "--noconfirm",
                "--onefile",
                "--windowed",
                "--name",
                "openbeat-installer",
                "--add-data",
                f"{payload_dir};payload",
                str(installer_entry),
            ],
            cwd=tmp_path,
        )

        generated = tmp_path / "dist" / "openbeat-installer.exe"
        if not generated.exists():
            raise FileNotFoundError(f"Expected installer executable at {generated}")
        shutil.copy2(generated, output_exe)

    return output_exe


def main() -> int:
    parser = argparse.ArgumentParser(description="Build OpenBeat single-file installers")
    parser.add_argument("--platform", choices=["macos", "windows", "all"], default="all")
    parser.add_argument("--python", default="python", help="Python executable to run PyInstaller")
    args = parser.parse_args()

    clean()
    version = parse_version()

    outputs: list[Path] = []
    if args.platform in ("macos", "all"):
        cli_binary = build_cli_binary(platform="macos", python_bin=args.python)
        outputs.append(create_macos_pkg(cli_binary=cli_binary, version=version))

    if args.platform in ("windows", "all"):
        cli_binary = build_cli_binary(platform="windows", python_bin=args.python)
        outputs.append(create_windows_exe(cli_binary=cli_binary, version=version, python_bin=args.python))

    for output in outputs:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
