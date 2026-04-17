# OpenBeat

OpenBeat is a free, open-source alternative to Beat Edit for DaVinci Resolve, designed to work in the free version of Resolve where `UIManager`-based tools no longer run.

## Why this exists

Beat Edit for Resolve depends on Fusion `UIManager` windows. Blackmagic intentionally restricted that UI path in Resolve Free starting with Resolve `19.1`, which breaks Beat Edit even though ordinary no-UI menu scripts still run. OpenBeat avoids that blocked UI path and instead ships Resolve-Free-compatible scripts under `Workspace > Scripts`.

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

### 1. Create the Python environment

```bash
cd /Users/parker/Documents/Code/OpenBeat
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

### 2. Link the Resolve scripts

```bash
cd /Users/parker/Documents/Code/OpenBeat
./scripts/install_resolve_scripts.sh
```

Restart Resolve after linking the scripts if it is already open.

## Outputs

- Click tracks are written next to the source file:
  - `*.openbeat-clicks.wav`
  - `*.openbeat-raw-clicks.wav`
- Subtitle files are written next to the source file:
  - `*.openbeat.srt`
  - `*.openbeat-raw.srt`

## Notes

- OpenBeat intentionally avoids custom popup UIs so it stays compatible with Resolve Free.
- Timeline and subtitle actions target all matching uses of the source file in the active timeline.
- Beat click actions render a WAV next to the source file and import it into the Media Pool for drag-and-drop use.
- Resolve's current scripting API still does not place audio-only clipInfos reliably at a chosen record frame, so OpenBeat does not claim automatic click-track placement on the timeline.
- The entry point for choosing the source file is the audio clip under the playhead.
