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


def pyinstaller_binary(output_name: str, entry_module: str, python_bin: str = "python") -> Path:
    run(
        [
            python_bin,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--onefile",
            "--name",
            output_name,
            "-m",
            entry_module,
        ]
    )
    candidates = [DIST_ROOT / output_name, DIST_ROOT / f"{output_name}.exe"]
    built = next((path for path in candidates if path.exists()), None)
    if built is None:
        raise FileNotFoundError(f"Expected bundled binary at one of: {candidates}")
    return built


def build_cli_binary(python_bin: str = "python") -> Path:
    return pyinstaller_binary("openbeat", "openbeat.cli", python_bin=python_bin)


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


def create_macos_dmg(cli_binary: Path, version: str) -> Path:
    package_dir = DIST_INSTALLERS / f"OpenBeat-macos-{version}"
    if package_dir.exists():
        shutil.rmtree(package_dir)

    payload_dir = package_dir / "payload"
    copy_payload(payload_dir)

    bin_dir = payload_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cli_binary, bin_dir / "openbeat")
    (bin_dir / "openbeat").chmod(0o755)

    install_script = package_dir / "install.command"
    install_script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\"
PAYLOAD=\"$SCRIPT_DIR/payload\"
RESOLVE_ROOT=\"$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion\"
UTILITY_TARGET=\"$RESOLVE_ROOT/Scripts/Utility/OpenBeat\"
MODULE_TARGET=\"$RESOLVE_ROOT/Modules/OpenBeat\"

mkdir -p \"$RESOLVE_ROOT/Scripts/Utility\" \"$RESOLVE_ROOT/Modules\"
rm -rf \"$UTILITY_TARGET\" \"$MODULE_TARGET\"
cp -R \"$PAYLOAD/Utility/OpenBeat\" \"$UTILITY_TARGET\"
cp -R \"$PAYLOAD/Modules/OpenBeat\" \"$MODULE_TARGET\"
mkdir -p \"$MODULE_TARGET/bin\"
cp \"$PAYLOAD/bin/openbeat\" \"$MODULE_TARGET/bin/openbeat\"
chmod +x \"$MODULE_TARGET/bin/openbeat\"

cat > \"$MODULE_TARGET/OpenBeatConfig.local.lua\" <<EOF
return {
  python_bin = \"$MODULE_TARGET/bin/openbeat\",
}
EOF

echo \"OpenBeat installed to: $RESOLVE_ROOT\"
echo \"Restart Resolve if it is open.\"
"""
    )
    install_script.chmod(0o755)

    dmg_path = DIST_INSTALLERS / f"OpenBeat-macos-{version}.dmg"
    run(
        [
            "hdiutil",
            "create",
            "-volname",
            "OpenBeat Installer",
            "-srcfolder",
            str(package_dir),
            "-ov",
            "-format",
            "UDZO",
            str(dmg_path),
        ]
    )
    return dmg_path


def create_windows_exe(cli_binary: Path, version: str, python_bin: str = "python") -> Path:
    output_exe = DIST_INSTALLERS / f"OpenBeat-windows-{version}-installer.exe"
    with tempfile.TemporaryDirectory(prefix="openbeat-win-installer-") as tmp:
        tmp_path = Path(tmp)
        payload_dir = tmp_path / "payload"
        copy_payload(payload_dir)
        payload_bin_dir = payload_dir / "bin"
        payload_bin_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cli_binary, payload_bin_dir / "openbeat.exe")

        installer_entry = tmp_path / "windows_installer.py"
        installer_entry.write_text(
            """from __future__ import annotations

import shutil
import sys
from pathlib import Path


def resolve_payload_root() -> Path:
    if hasattr(sys, '_MEIPASS'):
        return Path(getattr(sys, '_MEIPASS')) / 'payload'
    return Path(__file__).resolve().parent / 'payload'


def main() -> int:
    payload = resolve_payload_root()

    appdata = Path.home() / 'AppData' / 'Roaming'
    if 'APPDATA' in __import__('os').environ:
        appdata = Path(__import__('os').environ['APPDATA'])

    resolve_root = appdata / 'Blackmagic Design' / 'DaVinci Resolve' / 'Support' / 'Fusion'
    utility_target = resolve_root / 'Scripts' / 'Utility' / 'OpenBeat'
    module_target = resolve_root / 'Modules' / 'OpenBeat'

    (resolve_root / 'Scripts' / 'Utility').mkdir(parents=True, exist_ok=True)
    (resolve_root / 'Modules').mkdir(parents=True, exist_ok=True)

    if utility_target.exists():
        shutil.rmtree(utility_target)
    if module_target.exists():
        shutil.rmtree(module_target)

    shutil.copytree(payload / 'Utility' / 'OpenBeat', utility_target)
    shutil.copytree(payload / 'Modules' / 'OpenBeat', module_target)
    (module_target / 'bin').mkdir(parents=True, exist_ok=True)
    shutil.copy2(payload / 'bin' / 'openbeat.exe', module_target / 'bin' / 'openbeat.exe')

    exe_path = (module_target / 'bin' / 'openbeat.exe').as_posix()
    config_text = f'return {{\\n  python_bin = "{exe_path}",\\n}}\\n'
    (module_target / 'OpenBeatConfig.local.lua').write_text(config_text, encoding='utf-8')

    print(f'OpenBeat installed to: {resolve_root}')
    print('Restart Resolve if it is open.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
"""
        )

        run(
            [
                python_bin,
                "-m",
                "PyInstaller",
                "--clean",
                "--noconfirm",
                "--onefile",
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
    cli_binary = build_cli_binary(python_bin=args.python)

    outputs: list[Path] = []
    if args.platform in ("macos", "all"):
        outputs.append(create_macos_dmg(cli_binary=cli_binary, version=version))

    if args.platform in ("windows", "all"):
        outputs.append(create_windows_exe(cli_binary=cli_binary, version=version, python_bin=args.python))

    for output in outputs:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
