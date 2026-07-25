# OpenBeat

OpenBeat is a free, open-source beat editing toolkit for DaVinci Resolve. It is built to work in the non-Studio version of DaVinci Resolve by avoiding the custom `UIManager` windows that no longer run there.

OpenBeat is an independent community project. It is not an official Resolve component and is not distributed or endorsed as part of any commercial third-party tool.

## What It Does

- Creates timeline markers at detected beat positions
- Creates clip markers on matching source clips and timeline instances
- Renders beat-click WAV files for manual timeline placement
- Exports beat-based subtitle files
- Supports both `Quantized` and `Raw Beats` analysis modes

## Get OpenBeat

Free beat editing tools for DaVinci Resolve.

Download the macOS or Windows installer from the [latest GitHub Release](https://github.com/eimexdev/OpenBeat/releases/latest), or run OpenBeat from source. For step-by-step setup, update, and uninstall instructions, use [docs/install.md](docs/install.md). If you want source setup notes, use [docs/development.md](docs/development.md).

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
