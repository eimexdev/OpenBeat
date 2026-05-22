# Changelog

All notable OpenBeat changes should be summarized here for users. GitHub Releases can still use generated notes, but this file should keep the plain-language history easy to scan.

## 0.0.2 - 2026-04-19

- Bundled the OpenBeat runtime into macOS and Windows installer packages.
- Added release workflow support for attaching installer assets to GitHub Releases.
- Improved cross-platform Resolve script handling for bundled CLI execution.
- Kept OpenBeat as no-UI Resolve menu scripts for compatibility with the non-Studio Resolve workflow.

Known limits:

- Timeline markers and clip markers are the most reliable actions today.
- Click-track WAV files and subtitle SRT files are reliable generated outputs.
- Automatic click-track and subtitle placement on the timeline remains best-effort because of Resolve scripting limitations.

## 0.0.1 - 2026-04-19

- Initial pre-alpha release.
- Added beat analysis, timeline marker, clip marker, click-track, and subtitle export workflows.
- Added Quantized and Raw Beats modes.
