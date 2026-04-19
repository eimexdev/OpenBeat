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

Install build dependencies, then run:

```bash
python -m pip install . pyinstaller
python scripts/build_installers.py --platform all
```

Generated installer archives are written to `dist/installers/`.

## Current Technical Limits

- The non-Studio version of DaVinci Resolve does not reliably allow the kind of `UIManager` popup workflow used by older tools, so OpenBeat ships as no-UI menu scripts
- Audio click-track placement onto the timeline is not reliable enough to claim as automatic
- Subtitle-track population is still not reliable enough to claim as automatic
- Source resolution still depends on what Resolve exposes for the selected timeline item or the playhead clip

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
