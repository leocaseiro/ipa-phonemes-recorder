# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Peak and RMS measurement for 16-bit PCM WAV files.

The server controls the encode step (ffmpeg -c:a pcm_s16le), so we
only ever read 16-bit WAVs. Any other sample width raises.
"""

from __future__ import annotations

import array
import math
import wave
from pathlib import Path

DB_FLOOR = -60.0
INT16_MAX = 32768.0


def compute_peak_rms(path: Path) -> tuple[float, float, int]:
    """Return (peak_db, rms_db, duration_ms) for a 16-bit PCM WAV."""
    with wave.open(str(path), "rb") as w:
        nchannels = w.getnchannels()
        sampwidth = w.getsampwidth()
        framerate = w.getframerate()
        nframes = w.getnframes()
        if sampwidth != 2:
            raise ValueError(
                f"expected 16-bit PCM WAV, got sample width {sampwidth} bytes"
            )
        frames = w.readframes(nframes)

    if nframes == 0 or framerate == 0:
        return (DB_FLOOR, DB_FLOOR, 0)

    duration_ms = int(round(nframes / framerate * 1000))

    samples = array.array("h")
    samples.frombytes(frames)

    peak_int = 0
    sum_squares = 0.0
    count = 0

    if nchannels == 1:
        for s in samples:
            abs_s = -s if s < 0 else s
            if abs_s > peak_int:
                peak_int = abs_s
            sum_squares += s * s
            count += 1
    else:
        # Interleaved multi-channel: average per-frame, measure the mono mix.
        for i in range(0, len(samples) - (len(samples) % nchannels), nchannels):
            mixed = sum(samples[i + c] for c in range(nchannels)) / nchannels
            abs_m = -mixed if mixed < 0 else mixed
            if abs_m > peak_int:
                peak_int = abs_m
            sum_squares += mixed * mixed
            count += 1

    if count == 0:
        return (DB_FLOOR, DB_FLOOR, duration_ms)

    peak_lin = peak_int / INT16_MAX
    rms_lin = math.sqrt(sum_squares / count) / INT16_MAX

    return (_to_db(peak_lin), _to_db(rms_lin), duration_ms)


def _to_db(linear: float) -> float:
    if linear <= 0:
        return DB_FLOOR
    return round(max(DB_FLOOR, 20 * math.log10(linear)), 1)
