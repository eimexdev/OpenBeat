# User Guide

## Before You Start

OpenBeat works from the active timeline.

1. Select the target timeline audio clip
2. Run the action from `Workspace > Scripts > OpenBeat`
3. If that does not work, place the playhead over the target clip and run it again

## Choose A Mode

| Mode | Best for | Tradeoff |
| --- | --- | --- |
| `Quantized` | Music with a stable tempo, click-based edits, and clean marker spacing | Less faithful when the performance drifts or changes tempo |
| `Raw Beats` | Live performances, drift, rubato, and tempo changes | Less regular for count-based editing |

## Actions

### `Create Timeline Markers`

Adds markers to the timeline ruler for beats that land inside matching source segments in the active timeline.

- Re-running replaces only the previous OpenBeat timeline markers
- User-created timeline markers are left alone
- If the same source file appears multiple times, markers can appear across every matching use

### `Create Clip Markers`

Adds markers to both the Media Pool source clip and matching timeline clip instances.

- Matching instances are updated from source timing, not only from visible clip position
- If the same source appears multiple times, multiple instances can be updated
- User-created clip markers are left alone

### `Create Beat Click Audio`

Renders a click-track WAV next to the source file and imports it into the Media Pool.

- `Quantized` uses the estimated beat grid
- `Raw Beats` uses the detected beat times directly
- Manual drag-and-drop into the timeline is still the reliable workflow

### `Export Subtitles`

Writes an `.srt` file based on beat-to-beat ranges.

- Subtitle files are written relative to the active timeline start
- OpenBeat can try to import the file and create a subtitle track
- Treat the generated `.srt` as the reliable result

## Output Files

Generated files are written next to the source audio file.

- Quantized click track: `*.openbeat-clicks.wav`
- Raw click track: `*.openbeat-raw-clicks.wav`
- Quantized subtitles: `*.openbeat.srt`
- Raw subtitles: `*.openbeat-raw.srt`

If a file already exists, OpenBeat currently overwrites it.

## Troubleshooting

### OpenBeat picked the wrong clip

1. Select the target timeline item
2. If that does not work, place the playhead over the target audio clip
3. Run the action again

### The click track did not appear on the timeline

That is a current Resolve scripting limitation. Use the generated WAV from the Media Pool and place it manually.

### The subtitle track was created but stayed empty

That is also a current Resolve scripting limitation. Use the generated `.srt` file as the reliable output.

### Where to look for logs

macOS:

- Runtime log: `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/logs/OpenBeat.log`
- Analysis cache: `~/Library/Caches/OpenBeat`

Windows:

- Install folder: `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion`
- Runtime log: `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\logs\OpenBeat.log`
- Analysis cache: `%LOCALAPPDATA%\OpenBeat\Cache`

## Technical Details

### Source Selection

OpenBeat checks the timeline in this order:

1. The selected timeline item, if Resolve exposes it and it maps back to a usable audio source
2. The audio clip under the playhead

It does not use the selected Media Pool item as a fallback.

### Shared Behavior

- OpenBeat is timeline-driven, not Media Pool-driven
- Trimmed clips only receive beats inside the visible used range
- Timeline and subtitle actions can span all matching uses of the source file in the active timeline
- OpenBeat only removes markers it created itself
