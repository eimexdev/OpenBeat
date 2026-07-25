# Release Checklist

Use this checklist before publishing an OpenBeat release.

## Version

- Choose the next version number.
- Update `version` in `pyproject.toml`.
- Update `__version__` in `openbeat/__init__.py`.
- Confirm the release tag will be `v<version>`.

## Local Checks

Run from the repository root:

```bash
python -m compileall openbeat scripts tests
python -m unittest discover -s tests -v
```

If `lua` is available locally, also run:

```bash
lua -e 'assert(loadfile("resolve/Fusion/Modules/OpenBeat/OpenBeatCommon.lua"))'
```

## Installer Build

- Run the `Build Installers` workflow on the target commit.
- Confirm the macOS artifact is named `OpenBeat-macos-<version>.pkg`.
- Confirm the Windows artifact is named `OpenBeat-windows-<version>-installer.exe`.
- Download both artifacts and verify they are not stale local files.

## Smoke Test

On macOS:

- Run the `.pkg` installer.
- Restart Resolve.
- Confirm `Workspace > Scripts > OpenBeat` appears.
- Run `Create Timeline Markers (Quantized)` on a known test clip.

On Windows:

- Run the installer executable.
- Restart Resolve.
- Confirm `Workspace > Scripts > OpenBeat` appears.
- Run `Create Timeline Markers (Quantized)` on a known test clip.

For both platforms:

- Verify timeline marker creation.
- Verify clip marker creation.
- Verify click-track WAV generation.
- Verify subtitle SRT generation.
- Treat automatic click-track and subtitle timeline placement as best-effort only.

## Publish GitHub Release

- Confirm the chosen license is present before using open-source wording publicly.
- Run the `Release` workflow for the target tag and commit.
- Confirm the GitHub Release includes both installer assets:
  - `OpenBeat-macos-<version>.pkg`
  - `OpenBeat-windows-<version>-installer.exe`
- Confirm the release notes link to the changelog and accurately describe compatibility and known limitations.
- Publish the GitHub Release and mark it as the latest release.
- Open the [latest-release URL](https://github.com/eimexdev/OpenBeat/releases/latest) in an incognito browser and verify that both assets can be downloaded without signing in or completing a checkout.
- Confirm the repository is public before launch.

## Optional Ko-fi Support

- If Ko-fi is used, present it only as an optional way to support the project.
- Link Ko-fi visitors to the latest GitHub Release for downloads.
- Do not upload duplicate installer assets to Ko-fi or imply that payment, checkout, or a Ko-fi account is required.

## Site And Announcement

- Update every public download link to the latest GitHub Release.
- Confirm the GitHub source link points to the public repository.
- Publish the landing page.
- Post the launch announcement after the GitHub Release and public repository are live.
