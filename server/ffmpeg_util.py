# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Thin wrappers around the ffmpeg / ffprobe binaries.

The export pipeline (server/export.py) calls ffmpeg many times per
export, so a tiny helper here beats scattering subprocess boilerplate
across the module. Failures surface as `FfmpegError` with the stderr
tail preserved for debugging.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 60
STDERR_KEEP_BYTES = 2000


class FfmpegError(Exception):
    def __init__(self, message: str, *, stderr: str = "", returncode: int | None = None):
        self.message = message
        self.stderr = stderr
        self.returncode = returncode
        super().__init__(message)


def run(
    cmd: list[str],
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run ``cmd`` capturing stdout + stderr.

    Raises ``FfmpegError`` on non-zero exit or timeout when ``check`` is
    true; otherwise returns the ``CompletedProcess`` for the caller to
    inspect.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FfmpegError(
            f"command timed out after {timeout}s: {cmd[0]}",
            stderr=(exc.stderr or b"").decode("utf-8", errors="replace")[-STDERR_KEEP_BYTES:],
        ) from exc
    except FileNotFoundError as exc:
        raise FfmpegError(f"binary not found on PATH: {cmd[0]}") from exc

    if check and result.returncode != 0:
        raise FfmpegError(
            f"{Path(cmd[0]).name} exited {result.returncode}",
            stderr=result.stderr.decode("utf-8", errors="replace")[-STDERR_KEEP_BYTES:],
            returncode=result.returncode,
        )
    return result


def probe_duration_ms(path: Path, *, ffprobe: Path | None = None) -> int:
    """Return the duration of ``path`` in milliseconds via ``ffprobe``.

    If ``ffprobe`` is None, resolve from ``PATH`` (sibling of ffmpeg on
    any standard install).
    """
    binary = _resolve_ffprobe(ffprobe)
    result = run(
        [
            str(binary),
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    text = result.stdout.decode("utf-8", errors="replace").strip()
    try:
        seconds = float(text)
    except ValueError as exc:
        raise FfmpegError(
            f"ffprobe returned unparseable duration for {path}: {text!r}",
            stderr=result.stderr.decode("utf-8", errors="replace")[-STDERR_KEEP_BYTES:],
        ) from exc
    return int(round(seconds * 1000))


def _resolve_ffprobe(ffprobe: Path | None) -> Path:
    if ffprobe is not None:
        return ffprobe
    found = shutil.which("ffprobe")
    if not found:
        raise FfmpegError("ffprobe not found on PATH; install via brew install ffmpeg")
    return Path(found)
