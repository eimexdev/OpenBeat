from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = ROOT / "dist"
DIST_INSTALLERS = DIST_ROOT / "installers"
# Installed folders, relative to the Resolve Fusion support folder. The installers
# (staged_install.py and macos_postinstall.sh) replace exactly these folders.
PAYLOAD_DIRS = ("Modules/OpenBeat", "Scripts/Utility/OpenBeat")
# Where the macOS package installs its payload before the postinstall script copies
# it into the user's Resolve folder. It must match OPENBEAT_STAGING in
# macos_postinstall.sh, which refuses to run unless root alone can write to it.
MACOS_STAGING = "/Library/Application Support/OpenBeat/Installer"
MACOS_IDENTIFIER = "org.openbeat.installer"
# Mac architectures the package can carry a runtime for, as reported by uname -m.
# Each runtime is staged under payloads/<arch>; macos_postinstall.sh picks one.
MACOS_ARCHES = ("arm64", "x86_64")
# Oldest macOS the bundled runtimes run on. CI builds on macOS 15, where pip picks
# the numpy and scipy wheels built for macOS 14 and later.
MACOS_MINIMUM = "14.0"


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


def write_manifest(directory: Path) -> Path:
    """Record each file's SHA-256 so the installers can verify their staged copy before using it."""
    lines = []
    files = sorted((path.relative_to(directory).as_posix(), path) for path in directory.rglob("*") if path.is_file())
    for name, path in files:
        if "\n" in name or "\\" in name:
            raise ValueError(f"Payload file name cannot be listed in a manifest: {name!r}")
        with path.open("rb") as handle:
            lines.append(f"{hashlib.file_digest(handle, 'sha256').hexdigest()}  {name}\n")
    manifest = directory.with_name(f"{directory.name}.sha256")
    manifest.write_text("".join(lines), encoding="utf-8", newline="\n")
    return manifest


def build_payload(payload_root: Path, cli_binary: Path, platform: str) -> None:
    """Lay out the installed folders as they appear under the Resolve Fusion support folder."""
    for relative in PAYLOAD_DIRS:
        shutil.copytree(
            ROOT / "resolve" / "Fusion" / relative,
            payload_root / relative,
            ignore=shutil.ignore_patterns("OpenBeatConfig.local.lua", ".DS_Store"),
        )

    bin_dir = payload_root / "Modules" / "OpenBeat" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    if platform == "macos":
        shutil.copy2(cli_binary, bin_dir / "openbeat")
        (bin_dir / "openbeat").chmod(0o755)
    elif cli_binary.parent.name == "openbeat":
        shutil.copytree(cli_binary.parent, bin_dir / "openbeat")
    else:
        shutil.copy2(cli_binary, bin_dir / "openbeat.exe")

    # The runtime bundles FFmpeg (LGPL) and other third-party libraries; ship their notices.
    for notice in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / notice, payload_root / "Modules" / "OpenBeat" / notice)

    for relative in PAYLOAD_DIRS:
        write_manifest(payload_root / relative)


def restrict_modes(root: Path) -> None:
    """Make every folder and file writable only by its owner, which the package sets to root."""
    for path in [root, *root.rglob("*")]:
        if path.is_symlink():
            raise ValueError(f"The macOS package payload cannot contain symlinks: {path}")
        executable = path.is_dir() or path.stat().st_mode & 0o111
        path.chmod(0o755 if executable else 0o644)


def python_machine(python_bin: str) -> str:
    """The architecture that python_bin runs as, and so the architecture PyInstaller builds for."""
    result = subprocess.run(
        [python_bin, "-c", "import platform; print(platform.machine())"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def parse_macos_runtime(value: str) -> tuple[str, Path]:
    arch, separator, path = value.partition("=")
    if not separator or arch not in MACOS_ARCHES or not path:
        raise argparse.ArgumentTypeError(f"expected ARCH=PATH with ARCH one of {', '.join(MACOS_ARCHES)}, got {value!r}")
    return arch, Path(path)


def macos_distribution(version: str, component: str, arches: list[str]) -> str:
    """Product definition for productbuild.

    Listing every architecture the package has a runtime for in hostArchitectures
    lets Installer run the postinstall script natively on Apple silicon instead
    of asking for Rosetta, and refuses the package on a Mac it has no runtime for.
    """
    return f"""<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
    <title>OpenBeat {escape(version)}</title>
    <options customize="never" require-scripts="false" hostArchitectures={quoteattr(",".join(arches))}/>
    <domains enable_anywhere="false" enable_currentUserHome="false" enable_localSystem="true"/>
    <volume-check>
        <allowed-os-versions>
            <os-version min={quoteattr(MACOS_MINIMUM)}/>
        </allowed-os-versions>
    </volume-check>
    <choices-outline>
        <line choice={quoteattr(MACOS_IDENTIFIER)}/>
    </choices-outline>
    <choice id={quoteattr(MACOS_IDENTIFIER)} visible="false" title="OpenBeat">
        <pkg-ref id={quoteattr(MACOS_IDENTIFIER)}/>
    </choice>
    <pkg-ref id={quoteattr(MACOS_IDENTIFIER)} version={quoteattr(version)} onConclusion="none">{escape(component)}</pkg-ref>
</installer-gui-script>
"""


def create_macos_pkg(runtimes: dict[str, Path], version: str) -> Path:
    """Build one package holding a runtime for each architecture in runtimes."""
    unknown = sorted(set(runtimes) - set(MACOS_ARCHES))
    if not runtimes or unknown:
        raise ValueError(f"Expected runtimes for {', '.join(MACOS_ARCHES)}, got {sorted(runtimes)}")
    arches = [arch for arch in MACOS_ARCHES if arch in runtimes]
    with tempfile.TemporaryDirectory(prefix="openbeat-macos-installer-") as tmp:
        tmp_path = Path(tmp)
        root_dir = tmp_path / "root"
        for arch in arches:
            build_payload(root_dir / "payloads" / arch, runtimes[arch], "macos")
        restrict_modes(root_dir)

        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        postinstall = scripts_dir / "postinstall"
        shutil.copy2(ROOT / "scripts" / "macos_postinstall.sh", postinstall)
        postinstall.chmod(0o755)

        components = tmp_path / "components"
        components.mkdir()
        component = "OpenBeat-component.pkg"
        run(
            [
                "pkgbuild",
                "--identifier",
                MACOS_IDENTIFIER,
                "--version",
                version,
                "--root",
                str(root_dir),
                "--ownership",
                "recommended",
                "--scripts",
                str(scripts_dir),
                "--install-location",
                MACOS_STAGING,
                str(components / component),
            ]
        )

        distribution = tmp_path / "distribution.xml"
        distribution.write_text(macos_distribution(version, component, arches), encoding="utf-8")
        pkg_path = DIST_INSTALLERS / f"OpenBeat-macos-{version}.pkg"
        run(
            [
                "productbuild",
                "--distribution",
                str(distribution),
                "--package-path",
                str(components),
                str(pkg_path),
            ]
        )
        return pkg_path


def create_windows_exe(cli_binary: Path, version: str, python_bin: str = "python") -> Path:
    output_exe = DIST_INSTALLERS / f"OpenBeat-windows-{version}-installer.exe"
    with tempfile.TemporaryDirectory(prefix="openbeat-win-installer-") as tmp:
        tmp_path = Path(tmp)
        payload_dir = tmp_path / "payload"
        build_payload(payload_dir, cli_binary, "windows")

        installer_entry = tmp_path / "windows_installer.py"
        shutil.copy2(ROOT / "scripts" / "windows_installer.py", installer_entry)
        shutil.copy2(ROOT / "scripts" / "staged_install.py", tmp_path / "staged_install.py")

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
    parser.add_argument(
        "--platform",
        choices=["macos", "macos-runtime", "windows", "all"],
        default="all",
        help="macos-runtime builds only this Mac's runtime, for packaging with --macos-runtime elsewhere",
    )
    parser.add_argument("--python", default="python", help="Python executable to run PyInstaller")
    parser.add_argument(
        "--macos-runtime",
        action="append",
        default=[],
        type=parse_macos_runtime,
        metavar="ARCH=PATH",
        help="Package a prebuilt macOS runtime instead of building one; repeat for each architecture",
    )
    args = parser.parse_args()
    runtimes = dict(args.macos_runtime)
    if len(runtimes) != len(args.macos_runtime):
        parser.error("--macos-runtime lists the same architecture twice")
    if runtimes and args.platform not in ("macos", "all"):
        parser.error("--macos-runtime only applies to --platform macos")

    clean()
    version = parse_version()

    outputs: list[Path] = []
    if args.platform == "macos-runtime":
        outputs.append(build_cli_binary(platform="macos", python_bin=args.python))

    if args.platform in ("macos", "all"):
        if not runtimes:
            arch = python_machine(args.python)
            if arch not in MACOS_ARCHES:
                parser.error(f"Cannot build a macOS runtime for {arch!r}")
            runtimes[arch] = build_cli_binary(platform="macos", python_bin=args.python)
        outputs.append(create_macos_pkg(runtimes=runtimes, version=version))

    if args.platform in ("windows", "all"):
        cli_binary = build_cli_binary(platform="windows", python_bin=args.python)
        outputs.append(create_windows_exe(cli_binary=cli_binary, version=version, python_bin=args.python))

    for output in outputs:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
