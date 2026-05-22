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

## Publish

- Trigger the `Release` workflow with tag `v<version>`.
- Keep `draft` enabled for the first run.
- Check the generated release notes.
- Check both installer assets are attached to the draft release.
- Replace or supplement generated notes with concise install and known-limit notes.
- Publish the release.

## Site And Announcement

- Update the landing page download link to the published GitHub release or exact release assets.
- Confirm the GitHub repository is public before launch.
- Confirm the chosen license is present before using open-source wording publicly.
- Publish the landing page.
- Post the launch announcement after the download link and release assets are live.
