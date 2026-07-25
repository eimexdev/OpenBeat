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

- Optionally run `Build Installers` manually on the target commit for a preflight test without creating a release. Push and pull-request runs build the installers but do not upload them; manual-run artifacts expire after seven days.
- Run the manual `Release` workflow for the target and version tag with **Save as draft** enabled. The workflow calls `Build Installers` and attaches its newly built installers to the draft GitHub Release.
- Download both installer assets from the draft GitHub Release. These release assets, not artifacts from a separate manual build, are the files to smoke-test and distribute.
- Confirm the macOS artifact is named `OpenBeat-macos-<version>.pkg`.
- Confirm the Windows artifact is named `OpenBeat-windows-<version>-installer.exe`.
- Verify both files came from the draft GitHub Release, not from a local build or an older workflow run.

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
- Confirm the draft release notes link to the changelog and accurately describe compatibility and known limitations.
- Publish the draft GitHub Release containing the smoke-tested macOS `.pkg` and Windows installer `.exe`, and mark it as the latest release.
- Confirm the GitHub Release includes both installer assets:
  - `OpenBeat-macos-<version>.pkg`
  - `OpenBeat-windows-<version>-installer.exe`
- Confirm the published Release still contains the exact installer assets that were smoke-tested.
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
