# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Bank config validation.

`validate_config` returns a list of human-readable error strings. An
empty list means the config is valid.
"""

from __future__ import annotations

import re
from typing import Any

PRIVACY_VALUES = ("public", "private")
PHONEME_ID_RE = re.compile(r"^[a-z0-9_]+$")
REQUIRED_FIELDS = ("name", "locale", "privacy", "phonemes")


def validate_config(config: Any) -> list[str]:
    errors: list[str] = []

    if not isinstance(config, dict):
        return ["config must be a JSON object"]

    for field in REQUIRED_FIELDS:
        if field not in config:
            errors.append(f"missing required field: {field}")
    if errors:
        return errors

    if not isinstance(config["name"], str) or not config["name"].strip():
        errors.append("name must be a non-empty string")
    if not isinstance(config["locale"], str) or not config["locale"].strip():
        errors.append("locale must be a non-empty string")

    if config["privacy"] not in PRIVACY_VALUES:
        errors.append(
            f"privacy must be one of {PRIVACY_VALUES}, got {config['privacy']!r}"
        )
    elif config["privacy"] == "public":
        attribution = config.get("attribution")
        if not isinstance(attribution, str) or not attribution.strip():
            errors.append("attribution is required and non-empty when privacy is public")

    if "target_lufs" in config and not isinstance(config["target_lufs"], (int, float)):
        errors.append("target_lufs must be a number")

    errors.extend(_validate_phonemes(config["phonemes"]))
    return errors


def _validate_phonemes(phonemes: Any) -> list[str]:
    if not isinstance(phonemes, list) or not phonemes:
        return ["phonemes must be a non-empty array"]

    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_ipa: set[str] = set()

    for i, p in enumerate(phonemes):
        if not isinstance(p, dict):
            errors.append(f"phonemes[{i}] must be an object")
            continue

        pid = p.get("id")
        if not isinstance(pid, str) or not PHONEME_ID_RE.match(pid):
            errors.append(
                f"phonemes[{i}].id must match {PHONEME_ID_RE.pattern!r}"
            )
        elif pid in seen_ids:
            errors.append(f"duplicate phoneme id: {pid!r}")
        else:
            seen_ids.add(pid)

        ipa = p.get("ipa")
        if not isinstance(ipa, str) or not ipa:
            errors.append(f"phonemes[{i}].ipa must be a non-empty string")
        elif ipa in seen_ipa:
            errors.append(f"duplicate phoneme ipa: {ipa!r}")
        else:
            seen_ipa.add(ipa)

        if "example" in p:
            ex = p["example"]
            if isinstance(ex, str):
                pass
            elif isinstance(ex, list) and all(isinstance(e, str) for e in ex):
                pass
            else:
                errors.append(
                    f"phonemes[{i}].example must be a string or list of strings"
                )
        if "loopable" in p and not isinstance(p["loopable"], bool):
            errors.append(f"phonemes[{i}].loopable must be a boolean")
        if "category" in p and not isinstance(p["category"], str):
            errors.append(f"phonemes[{i}].category must be a string")

    return errors
