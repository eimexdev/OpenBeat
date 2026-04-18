# OpenBeat

OpenBeat is a free, open-source beat editing toolkit for DaVinci Resolve, designed to work in the free version of Resolve where `UIManager`-based tools no longer run.

## Why this exists

Beat Edit for Resolve depends on Fusion `UIManager` windows. Blackmagic intentionally restricted that UI path in Resolve Free starting with Resolve `19.1`, which breaks Beat Edit even though ordinary no-UI menu scripts still run. OpenBeat avoids that blocked UI path and instead ships Resolve-Free-compatible scripts under `Workspace > Scripts`.

OpenBeat is an independent community project. It is not an official Resolve component and is not distributed or endorsed as part of any commercial third-party tool.

## Current workflow

1. Put the playhead over the timeline audio clip you want to process.
2. Run one of the OpenBeat scripts from `Workspace > Scripts > OpenBeat`.
3. OpenBeat uses the source audio file under the playhead and applies the chosen action.

Available actions:

- `Create Timeline Markers (Quantized)`
- `Create Timeline Markers (Raw Beats)`
- `Create Clip Markers (Quantized)`
- `Create Clip Markers (Raw Beats)`
- `Create Beat Click Audio (Quantized)`
- `Create Beat Click Audio (Raw Beats)`
- `Export Subtitles (Quantized)`
- `Export Subtitles (Raw Beats)`

## Installation

### Option A (recommended): single-file installer download (no Python required)

CI now builds platform-specific single-file installers that bundle the OpenBeat CLI runtime:

- macOS artifact: `OpenBeat-macos-<version>.dmg`
- Windows artifact: `OpenBeat-windows-<version>-installer.exe`

On macOS, open the DMG and run `install.command`. On Windows, run the installer `.exe` directly.
Restart Resolve after install.

### Option B: developer install from source

#### 1. Create the Python environment

```bash
cd /Users/parker/Documents/Code/OpenBeat
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

#### 2. Link the Resolve scripts

```bash
cd /Users/parker/Documents/Code/OpenBeat
./scripts/install_resolve_scripts.sh
```

Restart Resolve after linking the scripts if it is already open.

## Building installers locally

Install build dependencies, then run:

```bash
python -m pip install . pyinstaller
python scripts/build_installers.py --platform all
```

Generated installer archives are written to `dist/installers/`.

## Outputs

- Click tracks are written next to the source file:
  - `*.openbeat-clicks.wav`
  - `*.openbeat-raw-clicks.wav`
- Subtitle files are written next to the source file:
  - `*.openbeat.srt`
  - `*.openbeat-raw.srt`
  - These subtitle files are now authored against the active timeline start so Resolve interprets them as timeline-relative captions.

## Notes

- OpenBeat intentionally avoids custom popup UIs so it stays compatible with Resolve Free.
- Timeline and subtitle actions target all matching uses of the source file in the active timeline.
- Clip marker actions write markers to both the source Media Pool item and each matching timeline clip instance.
- Beat click actions render a WAV next to the source file and import it into the Media Pool for drag-and-drop use.
- Resolve's current scripting API still does not place audio-only clipInfos reliably at a chosen record frame, so OpenBeat does not claim automatic click-track placement on the timeline.
- Resolve's subtitle import path is also still unreliable through scripting on Resolve Free `20.3.2`; OpenBeat generates/imports the `.srt`, but subtitle-track population is not yet reliable enough to claim as automatic.
- The entry point for choosing the source file is the audio clip under the playhead.
