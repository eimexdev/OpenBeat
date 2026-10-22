# Third-Party Notices

OpenBeat itself is released under the MIT License (see `LICENSE`). The installers also bundle a Python runtime and these libraries, each under its own license:

## FFmpeg

The installers include FFmpeg's libraries (libavcodec, libavformat, libavutil, libswresample, and related libraries) as shipped in the [PyAV](https://github.com/PyAV-Org/PyAV) wheels. OpenBeat uses them to read M4A, AAC, and the audio of video files.

- License: GNU Lesser General Public License, version 3 or later (LGPL-3.0-or-later). FFmpeg is built without `--enable-gpl` or `--enable-nonfree`.
- License text: <https://www.gnu.org/licenses/lgpl-3.0.html>
- Source: <https://ffmpeg.org/download.html>. The FFmpeg build used by PyAV is produced by <https://github.com/PyAV-Org/pyav-ffmpeg>.

FFmpeg is a trademark of Fabrice Bellard, originator of the FFmpeg project. To use a modified FFmpeg, rebuild the installer from this repository's source following `docs/development.md`, with PyAV linked against your FFmpeg build.

## Python packages

- PyAV: BSD-3-Clause
- librosa: ISC
- NumPy: BSD-3-Clause
- SciPy: BSD-3-Clause
- numba: BSD-2-Clause
- llvmlite: BSD-2-Clause, with LLVM under Apache-2.0 WITH LLVM-exception
- soundfile: BSD-3-Clause, with libsndfile under LGPL-2.1-or-later
- soxr (python-soxr): LGPL-2.1-or-later
- scikit-learn: BSD-3-Clause
- CPython: Python Software Foundation License

The exact versions are listed in `requirements/build.txt`.
