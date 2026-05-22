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

## Publish Source

- Confirm the chosen license is present before using open-source wording publicly.
- Publish a GitHub source release or tag for the version.
- Do not attach installer builds to public GitHub releases if builds are meant to be distributed through Ko-fi.
- Confirm the repository is public before launch.

## Publish Ko-fi Build

- Create or update the Ko-fi Shop digital product for OpenBeat.
- Upload the macOS and Windows installer assets.
- Set the product price to free.
- Keep support optional in the listing copy.
- Add preview images, summary, install notes, and known limitations.
- Add a post-purchase message that thanks supporters and tells them to restart Resolve after installing.
- Test the listing in an incognito browser and confirm the free checkout/download path works.

## Site And Announcement

- Update the landing page download link to the Ko-fi product listing.
- Confirm the GitHub source link points to the public repository.
- Publish the landing page.
- Post the launch announcement after the Ko-fi download link and source repository are live.
