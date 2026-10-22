# Install OpenBeat

Use the installer package for normal editing work. The installers include the OpenBeat runtime, so you do not need to install Python or project dependencies separately.

## Download

Installer builds are free downloads from the [latest GitHub Release](https://github.com/eimexdev/OpenBeat/releases/latest). No checkout or Ko-fi account is required.

1. Open the latest GitHub Release.
2. Under **Assets**, download the installer for your operating system:
   - macOS: `OpenBeat-macos-<version>.pkg`, for both Apple silicon and Intel Macs
   - Windows: `OpenBeat-windows-<version>-installer.exe`
3. Close DaVinci Resolve before running the installer.

If OpenBeat saves you time, you may support the project on Ko-fi, but support is optional and all installer downloads remain on GitHub Releases.

If you prefer source builds, the public repository includes development setup and local installer build notes in [development.md](development.md).

## macOS

OpenBeat needs macOS 14 Sonoma or later. The same package works on Apple silicon and Intel Macs: it contains a runtime for each and installs the one that matches your Mac, without needing Rosetta.

1. Run the `.pkg` installer. The first time, macOS blocks it; see [First Install Warnings](#first-install-warnings).
2. Restart DaVinci Resolve.
3. Confirm the scripts appear under `Workspace > Scripts > OpenBeat`.

The installer copies OpenBeat into:

- Scripts: `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/OpenBeat`
- Modules: `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Modules/OpenBeat`

## Windows

1. Run `OpenBeat-windows-<version>-installer.exe`. The first time, Windows warns about it; see [First Install Warnings](#first-install-warnings).
2. Accept the default Resolve Fusion support folder unless you have moved Resolve's scripting support files.
3. Restart DaVinci Resolve.
4. Confirm the scripts appear under `Workspace > Scripts > OpenBeat`.

The installer copies OpenBeat into:

- Scripts: `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\OpenBeat`
- Modules: `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Modules\OpenBeat`

## First Install Warnings

OpenBeat's installers are not code-signed yet, so macOS and Windows warn that they come from an unknown developer. This happens once per download. The installers are built in public by the repository's GitHub Actions workflows, and each release's notes name the commit it was built from.

### macOS

On macOS 15 Sequoia and later:

1. Double-click the `.pkg`. macOS says it "Not Opened" because Apple could not verify it. Click **Done**.
2. Open **System Settings > Privacy & Security** and scroll to **Security**. Next to the message that the OpenBeat package was blocked, click **Open Anyway**.
3. If macOS asks, confirm with your password or Touch ID. When the warning appears again, click **Open** (some macOS versions label it **Open Anyway**). The installer starts.

The **Open Anyway** button appears for about an hour after you try to open the package. If it is missing, double-click the package again first.

On macOS 14 Sonoma, Control-click the `.pkg`, choose **Open**, then click **Open** in the dialog.

You only need to do this for the installer. Once installed, Resolve runs OpenBeat without further prompts.

### Windows

1. Your browser may say the file isn't commonly downloaded. In Edge, open the download's **...** menu and choose **Keep**, then **Show more > Keep anyway**. In Chrome, choose **Keep**.
2. When you run the installer, Microsoft Defender SmartScreen shows "Windows protected your PC". Click **More info**, then **Run anyway**.

If Windows 11 says **Smart App Control** blocked the installer, there is no "Run anyway" option. Smart App Control can block unsigned apps that Microsoft's reputation service doesn't know yet, which may include a new OpenBeat release, and it has no per-app exception. You can turn it off in **Windows Security > App & browser control > Smart App Control settings**. On an up-to-date Windows 11 you can turn it back on there later; older versions only let you turn it back on by resetting Windows. Signed Windows installers are planned.

## Update

Install the newer package over the old one, then restart Resolve. The installer replaces the OpenBeat script and module folders, but it does not remove your project markers, generated click tracks, generated subtitle files, or analysis cache.

The installer copies the new files next to your current installation and checks them before replacing anything. If copying, checking, or replacing fails, for example because the disk is full or Resolve still has OpenBeat files open, your current installation is kept and the installer reports that it did not complete. Close Resolve and run the installer again. On macOS, Installer's log (**Window > Installer Log**) shows the reason.

On macOS, OpenBeat 0.0.1 could leave some Resolve folders owned by root if Resolve had never been opened. If the installer log says OpenBeat cannot write to a folder, run the `sudo chown` command it shows in Terminal, then run the installer again.

If an update is cut off part way through, for example by a power failure, run the installer again. It first puts back the previous installation it had set aside, then repeats the update. It also removes any `.OpenBeat.new`, `.OpenBeat.old`, or `.OpenBeat.discard` folders left next to the OpenBeat folders.

## Uninstall

Delete the OpenBeat script and module folders listed above, then restart Resolve.

## Verify The Install

1. Open a Resolve project and timeline.
2. Place the playhead over a timeline audio clip.
3. Run `Workspace > Scripts > OpenBeat > Create Timeline Markers (Quantized)`.

If multiple audio clips overlap the playhead, OpenBeat uses the usable source on the lowest-numbered audio track.

## Current Compatibility

OpenBeat is designed for the non-Studio version of DaVinci Resolve by avoiding custom `UIManager` windows. Local testing has confirmed the core workflow in DaVinci Resolve 20.3.2. Studio builds may work too, but the release target is the free/non-Studio workflow.

OpenBeat is an independent community project. It is not an official Resolve component and is not distributed or endorsed by Blackmagic Design.
