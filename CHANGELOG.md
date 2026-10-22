# Changelog

All notable OpenBeat changes should be summarized here for users. GitHub Releases can still use generated notes, but this file should keep the plain-language history easy to scan.

## 0.1.0

- OpenBeat is now released under the MIT License.
- OpenBeat now reads M4A and AAC audio and the audio track of video files such as MOV, MP4, and MXF, using FFmpeg decoders bundled in the installers. WAV, AIFF, FLAC, OGG Vorbis, and MP3 still work as before.
- A damaged file, or a video with no audio track, now gives a short message instead of a Python error.
- Installer updates now prepare and verify the new files before replacing the installed ones. If an update fails or is interrupted, the previous installation is kept or restored by running the installer again.
- The macOS installer now works on Intel Macs as well as Apple silicon. One package contains a runtime for each and installs the right one. It requires macOS 14 Sonoma or later.
- The macOS installer stages its files in a folder only root can change, instead of a shared temporary folder, and stops with a clear error if it cannot tell which user to install for.
- Release builds use one resolved commit for testing, building, and tagging, and pinned build dependencies.
- When beat analysis or click-track rendering fails, OpenBeat now shows the helper's error instead of a missing-file error, and no longer imports an older click track as if it were new.
- On Windows, OpenBeat should now work when the Windows user name or the media path contains non-English characters, such as `José` or `Música`. Subtitle export to such folders is not fixed yet.

Known limits:

- The installers are not code-signed yet, so macOS and Windows show a warning the first time you run them. See the install guide for how to continue.
- Windows 11 Smart App Control may block the unsigned Windows installer, with no option to run it anyway.
- Automatic click-track and subtitle placement on the timeline remains best-effort.

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
