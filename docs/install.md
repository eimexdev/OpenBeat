# Install OpenBeat

Use the installer package for normal editing work. The installers include the OpenBeat runtime, so you do not need to install Python or project dependencies separately.

## Download

Installer builds are distributed through Ko-fi as a pay-what-you-want digital download. You can enter `$0` to download for free, or add support if OpenBeat saves you time.

1. Open the OpenBeat Ko-fi shop listing.
2. Choose the amount you want to pay. `$0` is fine.
3. Download the installer for your operating system:
   - macOS: `OpenBeat-macos-<version>.pkg`
   - Windows: `OpenBeat-windows-<version>-installer.exe`
4. Close DaVinci Resolve before running the installer.

If you prefer source builds, the public repository includes development setup and local installer build notes in [development.md](development.md).

## macOS

1. Run the `.pkg` installer.
2. If macOS Gatekeeper blocks the package, open System Settings > Privacy & Security and allow the package, then run it again.
3. Restart DaVinci Resolve.
4. Confirm the scripts appear under `Workspace > Scripts > OpenBeat`.

The installer copies OpenBeat into:

- Scripts: `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/OpenBeat`
- Modules: `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Modules/OpenBeat`

## Windows

1. Run `OpenBeat-windows-<version>-installer.exe`.
2. Accept the default Resolve Fusion support folder unless you have moved Resolve's scripting support files.
3. Restart DaVinci Resolve.
4. Confirm the scripts appear under `Workspace > Scripts > OpenBeat`.

The installer copies OpenBeat into:

- Scripts: `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\OpenBeat`
- Modules: `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Modules\OpenBeat`

## Update

Install the newer package over the old one, then restart Resolve. The installer replaces the OpenBeat script and module folders, but it does not remove your project markers, generated click tracks, generated subtitle files, or analysis cache.

## Uninstall

Delete the OpenBeat script and module folders listed above, then restart Resolve.

## Verify The Install

1. Open a Resolve project and timeline.
2. Select a timeline audio clip, or place the playhead over an audio clip.
3. Run `Workspace > Scripts > OpenBeat > Create Timeline Markers (Quantized)`.

If the script runs but cannot identify the clip, place the playhead over the target audio clip and run it again.

## Current Compatibility

OpenBeat is designed for the non-Studio version of DaVinci Resolve by avoiding custom `UIManager` windows. Local testing has confirmed the core workflow in DaVinci Resolve 20.3.2. Studio builds may work too, but the release target is the free/non-Studio workflow.

OpenBeat is an independent community project. It is not an official Resolve component and is not distributed or endorsed by Blackmagic Design.
