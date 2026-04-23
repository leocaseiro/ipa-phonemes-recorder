# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Bank discovery and read."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from dataclasses import asdict

from server.gitignore import verify as verify_gitignore
from server.schema import validate_config
from server.state import read_state

logger = logging.getLogger(__name__)

BANK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class BankNotFound(Exception):
    def __init__(self, bank_id: str):
        self.bank_id = bank_id
        super().__init__(f"bank not found: {bank_id!r}")


class BankInvalid(Exception):
    def __init__(self, bank_id: str, errors: list[str]):
        self.bank_id = bank_id
        self.errors = errors
        super().__init__(f"bank {bank_id!r} has invalid config: {errors}")


def list_banks(repo_root: Path) -> list[dict]:
    banks_dir = repo_root / "banks"
    if not banks_dir.is_dir():
        return []

    results: list[dict] = []
    for entry in sorted(banks_dir.iterdir()):
        if not entry.is_dir() or not BANK_ID_RE.match(entry.name):
            continue
        config_file = entry / "config.json"
        if not config_file.is_file():
            continue
        try:
            config = json.loads(config_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning("skipping %s: invalid JSON: %s", entry.name, exc)
            continue
        errors = validate_config(config)
        if errors:
            logger.warning("skipping %s: %s", entry.name, errors)
            continue
        results.append(
            {
                "id": entry.name,
                "name": config["name"],
                "locale": config["locale"],
                "privacy": config["privacy"],
                "phoneme_count": len(config["phonemes"]),
            }
        )
    return results


def read_bank(repo_root: Path, bank_id: str) -> dict:
    if not BANK_ID_RE.match(bank_id):
        raise BankNotFound(bank_id)

    bank_path = repo_root / "banks" / bank_id
    config_file = bank_path / "config.json"
    if not bank_path.is_dir() or not config_file.is_file():
        raise BankNotFound(bank_id)

    try:
        config = json.loads(config_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BankInvalid(bank_id, [f"config.json is not valid JSON: {exc}"]) from exc

    errors = validate_config(config)
    if errors:
        raise BankInvalid(bank_id, errors)

    state = read_state(bank_path)
    gitignore_status = verify_gitignore(bank_path, config["privacy"])
    return {
        "config": config,
        "state": state,
        "gitignore": asdict(gitignore_status),
    }
