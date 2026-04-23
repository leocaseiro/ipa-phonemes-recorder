# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Bank session state I/O.

`state.json` is written atomically via temp-file + os.replace so a
crash cannot produce a half-written file. A corrupt state.json is
quarantined to `state.json.corrupt-<ts>` and replaced with a fresh
empty state; raw WAVs are untouched.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def empty_state() -> dict:
    return {"last_phoneme_id": None, "last_input_device": None, "phonemes": {}}


def read_state(bank_path: Path) -> dict:
    state_file = bank_path / "state.json"
    if not state_file.is_file():
        return empty_state()
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        corrupt = state_file.with_name(f"state.json.corrupt-{ts}")
        state_file.rename(corrupt)
        logger.warning(
            "corrupt state.json in %s quarantined to %s: %s",
            bank_path,
            corrupt.name,
            exc,
        )
        return empty_state()


def write_state(bank_path: Path, state: dict) -> None:
    state_file = bank_path / "state.json"
    tmp = state_file.with_name("state.json.tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, state_file)
