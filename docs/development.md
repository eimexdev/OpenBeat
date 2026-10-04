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

Install build dependencies, then run the installer build for the current operating system:

```bash
python -m pip install . pyinstaller
python scripts/build_installers.py --platform macos
# or, on Windows:
python scripts/build_installers.py --platform windows
```

Generated installer archives are written to `dist/installers/`.

Installer builds are platform-specific. Build the macOS `.pkg` on macOS and the Windows `.exe` on Windows; PyInstaller does not cross-compile the bundled runtime.

## Release Workflow

GitHub Actions now has two installer-related workflows:

- `Build Installers`: runs on pull requests and pushes to `main` to test that both platform installers still build. Those automatic runs do not upload workflow artifacts. A manual run builds the same installers and uploads them as workflow artifacts retained for seven days.
- `Release`: manual-only. It calls `Build Installers`, receives that called workflow's uploaded artifacts, and attaches the installer files to a GitHub Release.

Use a manual `Build Installers` run when a contributor needs downloadable installers for testing a branch, tag, or commit without creating a release. Use `Release` when maintainers are preparing a version for distribution: its GitHub Release assets are the durable, public downloads. Workflow artifacts from a manual build are temporary test outputs, not release downloads.

The release workflow expects the repository version to already be updated in both `pyproject.toml` and `openbeat/__init__.py`. Trigger it with a tag like `v0.1.0`, and it will:

- build the installers from the selected branch or commit
- verify the tag matches the project version
- create the release
- use GitHub's generated release notes so the release body gets the standard `What's Changed` summary and full changelog link

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
