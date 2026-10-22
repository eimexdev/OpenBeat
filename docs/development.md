# Development Notes

## Source Setup

Use the installer packages for normal use. The steps below are for contributors and local testing.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
./scripts/install_resolve_scripts.sh
```

Restart Resolve after linking the scripts.

## What The Source Installer Does

The source install script:

- Symlinks `resolve/Fusion/Scripts/Utility/OpenBeat` into the user Resolve scripts folder
- Symlinks `resolve/Fusion/Modules/OpenBeat` into the user Resolve modules folder
- Writes `resolve/Fusion/Modules/OpenBeat/OpenBeatConfig.local.lua` with the repo path and local Python interpreter

Because the script points Resolve at this checkout and its `.venv`, it should be treated as a development setup rather than the normal end-user install path.

## Build Installers Locally

Install the pinned build dependencies, then run the installer build for the current operating system:

```bash
python -m pip install --require-hashes -r requirements/build.txt
python -m pip install --no-deps --no-build-isolation .
python scripts/build_installers.py --platform macos
# or, on Windows:
python scripts/build_installers.py --platform windows
```

Generated installer archives are written to `dist/installers/`.

A local macOS build contains only the runtime for the Mac it was built on, and its package installs only on Macs of that architecture. PyInstaller builds for the architecture of the Python running it, and numpy, scipy, and numba publish no `universal2` wheels, so the runtimes cannot be combined into one universal binary. To package both, build each runtime on a Mac of that architecture, then pass both to the package build:

```bash
# On an Apple silicon Mac, and again on an Intel Mac:
python scripts/build_installers.py --platform macos-runtime   # writes dist/openbeat

# On either Mac, with both runtimes copied over:
python scripts/build_installers.py --platform macos \
  --macos-runtime arm64=path/to/arm64/openbeat \
  --macos-runtime x86_64=path/to/x86_64/openbeat
```

The package build wraps the component package from `pkgbuild` in a product archive from `productbuild`. Its distribution file lists the architectures the package has runtimes for in `hostArchitectures`, so Installer runs the postinstall script natively on Apple silicon instead of asking for Rosetta, and requires macOS 14 or later (`MACOS_MINIMUM` in `scripts/build_installers.py`). The postinstall script picks `payloads/arm64` or `payloads/x86_64`, using `sysctl hw.optional.arm64` so an Apple silicon Mac gets the arm64 runtime even when the script runs under Rosetta.

The macOS 14 minimum comes from the wheels: on the macOS 15 build machines pip picks the numpy and scipy wheels built for macOS 14 and later, which the runtime bundles. Raise `MACOS_MINIMUM` if a dependency update needs a newer macOS.

## Build Dependencies

`requirements/build.txt` pins every package used to test and build the installers: the runtime dependencies from `pyproject.toml` and the build tools from `requirements/build.in`. It lists exact versions with SHA-256 hashes for macOS, Windows, and Linux; CI uses the Python 3.11 pins, and a few packages have separate pins for newer Python versions. CI installs it with `--require-hashes`, so rebuilding a release commit bundles the same packages. CI still upgrades pip itself before installing; pip installs the pinned packages but is not bundled into the installers.

To update the pins, edit `pyproject.toml` or `requirements/build.in` if needed, then regenerate the file with [uv](https://docs.astral.sh/uv/):

```bash
uv pip compile pyproject.toml requirements/build.in --constraint requirements/build-constraints.txt --universal --python-version 3.11 --generate-hashes --upgrade --output-file requirements/build.txt
```

Replace `--upgrade` with `--upgrade-package <name>` to move a single package, or omit it to keep the existing pins while adding or removing packages.

`requirements/build-constraints.txt` holds Intel Macs on numba 0.62, because numba 0.63 and later, and the llvmlite releases they need, publish no macOS x86_64 wheels. The lock therefore pins numba 0.62.1, llvmlite 0.45.1, and numpy 2.3.5 for the Intel Mac runtime and newer releases everywhere else. Every pin must have a wheel for each platform CI builds on, macOS x86_64 included; without one, `pip install --require-hashes` falls back to building from source, which fails for llvmlite. If a later numba restores macOS x86_64 wheels, or Intel support is dropped, remove the constraint. Review the version changes in the diff and open a pull request; its `Build Installers` run tests, builds, and smoke-tests both installers with the new pins.

## How Installers Replace An Existing Install

Both installers stage the new `Modules/OpenBeat` and `Scripts/Utility/OpenBeat` folders next to the installed ones as `.OpenBeat.new`, verify them against SHA-256 manifests written by `build_installers.py`, and only then rename the installed folders to `.OpenBeat.old` and the staged folders into place. Any failure renames `.OpenBeat.old` back, and the next run restores a `.OpenBeat.old` folder left by an interrupted update before it stages anything. The macOS package does this in `scripts/macos_postinstall.sh` and the Windows installer in `scripts/staged_install.py`; `tests/test_installer_updates.py` runs the same failed-update scenarios against both.

The macOS package installs its payload into `/Library/Application Support/OpenBeat/Installer`, and the postinstall script, which runs as root, checks that folder and works out the logged-in user, then copies the payload into that user's Resolve folder as the user (through `sudo -u`), so nothing in their home folder is changed with root's permissions. The script refuses to run unless that folder and every folder above it belong to root and only root can write to them, so another user on the Mac cannot place or swap the files it copies, and it deletes the folder afterwards. With nobody logged in, for example `sudo installer -pkg ... -target /` over SSH, it installs for the user who ran `sudo`; it stops with an error rather than install for root or a system account.

## Run Tests

Install Lua 5.1 or a later Lua release, then run `python -m unittest discover -s tests -v`. The suite tests timecode conversion, source selection, marker replacement and rollback, and subtitle timing without an open Resolve project. It also sends generated audio through the real CLI and checks both click-track modes.

After building an installer, test the bundled runtime with `python scripts/smoke_test_runtime.py dist/openbeat` on macOS or `python scripts/smoke_test_runtime.py dist/openbeat/openbeat.exe` on Windows. CI runs these checks on every runtime it builds: the macOS arm64 runtime on `macos-15`, the macOS x86_64 runtime on the Intel `macos-15-intel` runner, and the Windows runtime on `windows-latest`. The macOS package job then puts both macOS runtimes into one package, checks that each has the right architecture, installs the package on its runner, and runs the smoke test against the installed runtime. They verify analysis of WAV, MP3, M4A, MOV, and MP4 sources (the last three through the FFmpeg libraries bundled with PyAV), output generation, and the error shown for unreadable files; placement inside Resolve still needs a manual check.

Installer builds are platform-specific. Build the macOS `.pkg` on macOS and the Windows `.exe` on Windows; PyInstaller does not cross-compile the bundled runtime.

## Release Workflow

GitHub Actions now has two installer-related workflows:

- `Build Installers`: runs on pull requests and pushes to `main` to test that both platform installers still build. Those automatic runs do not upload installer artifacts; the macOS runtimes are passed to the package job as artifacts named `openbeat-macos-runtime-<arch>` that expire after a day. A manual run builds the same installers and uploads them as workflow artifacts retained for seven days.
- `Release`: manual-only. It calls `Build Installers`, receives that called workflow's uploaded artifacts, and attaches the installer files to a GitHub Release.

Use a manual `Build Installers` run when a contributor needs downloadable installers for testing a branch, tag, or commit without creating a release. Use `Release` when maintainers are preparing a version for distribution: its GitHub Release assets are the durable, public downloads. Workflow artifacts from a manual build are temporary test outputs, not release downloads.

The release workflow expects the repository version to already be updated in both `pyproject.toml` and `openbeat/__init__.py`. Trigger it with a tag like `v0.1.0`, and it will:

- resolve the selected branch or commit to a single commit SHA when the run starts
- verify the tag matches the project version and is not already used by a release or by a tag on another commit, before building anything
- test and build the installers from that commit, even if the branch moves during the run
- create the release with that commit as its target, so the tag is created on the tested commit, including when a draft is published later
- start the release notes with the commit SHA and a link to the run, followed by GitHub's generated `What's Changed` summary and full changelog link

Release from a commit that includes `requirements/build.txt`.

## Current Technical Limits

- The non-Studio version of DaVinci Resolve does not reliably allow the kind of `UIManager` popup workflow used by older tools, so OpenBeat ships as no-UI menu scripts
- Audio click-track placement onto the timeline is not reliable enough to claim as automatic
- Subtitle-track population is still not reliable enough to claim as automatic
- Source resolution uses the audio clip under the playhead, choosing the lowest-numbered usable audio track when clips overlap

## Verified Behavior

Local testing in the non-Studio version of DaVinci Resolve `20.3.2` confirmed:

- Timeline marker creation works
- Clip marker creation works
- Click-track WAV generation works
- Subtitle file generation works
- Click-track and subtitle timeline placement are still best-effort only

## Design Intent

OpenBeat is trying to preserve the useful core workflow of beat-editing tools while staying compatible with the non-Studio version of DaVinci Resolve:

- Beat analysis happens in Python
- Resolve scripts handle timeline-facing actions
- The shipped actions stay small and predictable
- User-facing docs stay focused on what editors can do right now
