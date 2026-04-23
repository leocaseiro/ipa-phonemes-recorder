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
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TAKE_ID_RE = re.compile(r"^take-\d{3,}$")


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


def validate_state_shape(state: Any) -> list[str]:
    """Structural checks for a state payload supplied by the client.

    Catches typos and forged writes. Does not cross-reference the bank
    config (the client may race with a config edit) and does not verify
    that raw WAV files exist on disk (disk is source of truth; state is
    allowed to lag).
    """
    errors: list[str] = []

    if not isinstance(state, dict):
        return ["state must be a JSON object"]

    if "last_phoneme_id" not in state:
        errors.append("missing key: last_phoneme_id")
    elif state["last_phoneme_id"] is not None and not isinstance(state["last_phoneme_id"], str):
        errors.append("last_phoneme_id must be a string or null")

    if "last_input_device" not in state:
        errors.append("missing key: last_input_device")
    elif state["last_input_device"] is not None and not isinstance(state["last_input_device"], str):
        errors.append("last_input_device must be a string or null")

    if "phonemes" not in state:
        errors.append("missing key: phonemes")
    elif not isinstance(state["phonemes"], dict):
        errors.append("phonemes must be an object")
    else:
        for pid, ph in state["phonemes"].items():
            errors.extend(_validate_phoneme_state(pid, ph))

    return errors


def _validate_phoneme_state(pid: str, ph: Any) -> list[str]:
    prefix = f"phonemes[{pid!r}]"
    errors: list[str] = []
    if not isinstance(ph, dict):
        return [f"{prefix} must be an object"]

    keeper = ph.get("keeper_take")
    if keeper is not None and not isinstance(keeper, str):
        errors.append(f"{prefix}.keeper_take must be a string or null")

    takes = ph.get("takes", [])
    if not isinstance(takes, list):
        errors.append(f"{prefix}.takes must be an array")
        return errors

    seen_ids: set[str] = set()
    for i, take in enumerate(takes):
        if not isinstance(take, dict):
            errors.append(f"{prefix}.takes[{i}] must be an object")
            continue
        tid = take.get("id")
        if not isinstance(tid, str) or not TAKE_ID_RE.match(tid):
            errors.append(f"{prefix}.takes[{i}].id must match take-NNN")
            continue
        if tid in seen_ids:
            errors.append(f"{prefix} has duplicate take id: {tid!r}")
        seen_ids.add(tid)

    if isinstance(keeper, str) and keeper not in seen_ids:
        errors.append(f"{prefix}.keeper_take {keeper!r} is not among the takes")

    return errors
