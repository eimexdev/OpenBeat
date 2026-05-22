# OpenBeat

OpenBeat is a free, open-source beat editing toolkit for DaVinci Resolve. It is built to work in the non-Studio version of DaVinci Resolve by avoiding the custom `UIManager` windows that no longer run there.

OpenBeat is an independent community project. It is not an official Resolve component and is not distributed or endorsed as part of any commercial third-party tool.

## What It Does

- Creates timeline markers at detected beat positions
- Creates clip markers on matching source clips and timeline instances
- Renders beat-click WAV files for manual timeline placement
- Exports beat-based subtitle files
- Supports both `Quantized` and `Raw Beats` analysis modes

## Install

Installer builds are free downloads through Ko-fi. Ko-fi also gives people a way to support the project if OpenBeat saves them time.

Download the installer for your operating system:

- macOS: `OpenBeat-macos-<version>.pkg`
- Windows: `OpenBeat-windows-<version>-installer.exe`

Close DaVinci Resolve before installing, then restart Resolve after the installer finishes. The installers bundle the OpenBeat runtime, so no separate Python setup is required.

For step-by-step install, update, and uninstall instructions, use [docs/install.md](docs/install.md). If you want to run from source or build installers locally, use [docs/development.md](docs/development.md).

## Use It

1. Select the target timeline audio clip.
2. Run an OpenBeat action from `Workspace > Scripts > OpenBeat`.
3. If Resolve does not expose the selection cleanly, place the playhead over the clip and run the action again.

Available actions:

- `Create Timeline Markers`
- `Create Clip Markers`
- `Create Beat Click Audio`
- `Export Subtitles`

Each action is available in both `Quantized` and `Raw Beats` variants.

## Current Status

- OpenBeat runs as menu scripts under `Workspace > Scripts > OpenBeat`
- Timeline markers and clip markers are the most reliable actions today
- Click tracks and subtitles are reliable as generated files, but automatic placement in the timeline is still best-effort
- Generated files are written next to the source audio file

## Docs

- [Install guide](docs/install.md)
- [User guide](docs/guide.md)
- [Development notes](docs/development.md)
- [Release checklist](docs/release-checklist.md)
- [Docs index](docs/README.md)
