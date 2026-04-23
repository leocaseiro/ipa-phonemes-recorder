# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Bank discovery and read."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import os
from dataclasses import asdict

from server.gitignore import sync as sync_gitignore
from server.gitignore import verify as verify_gitignore
from server.schema import validate_config
from server.state import empty_state, read_state, write_state

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


class BankIdExists(Exception):
    def __init__(self, bank_id: str):
        self.bank_id = bank_id
        super().__init__(f"bank {bank_id!r} already exists")


class CreateBankInvalid(Exception):
    """One or more fields in the create-bank payload are rejected."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


# BCP-47 subset — "xx", "xx-XX", optional script/region/variant blocks.
_LOCALE_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{1,8})*$")

# Supported inventory-source values. "copy:<bank-id>" is matched separately.
_INVENTORY_SOURCES = ("english-basic",)


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


def create_bank(*, repo_root: Path, seeds_dir: Path, payload: dict) -> dict:
    """Scaffold a new bank on disk and return the summary entry.

    Always creates with privacy="private"; flipping public is a separate
    PUT /api/banks/:id/config. Phoneme inventory comes from
    ``inventory_source``:
      - ``english-basic`` (default): read ``<seeds_dir>/english-basic.json``.
      - ``copy:<existing-bank-id>``: copy the phonemes array from that bank.

    Raises:
      - ``CreateBankInvalid`` with a specific ``code`` for input errors.
      - ``BankIdExists`` when ``banks/<id>/`` already exists.
    """
    bank_id = payload.get("id")
    name = payload.get("name")
    locale = payload.get("locale")
    speaker = payload.get("speaker")
    inventory_source = payload.get("inventory_source", "english-basic")

    if not isinstance(bank_id, str) or not BANK_ID_RE.match(bank_id):
        raise CreateBankInvalid(
            "invalid_id",
            f"id must match {BANK_ID_RE.pattern!r}; got {bank_id!r}",
        )
    if not isinstance(name, str) or not name.strip():
        raise CreateBankInvalid("invalid_name", "name must be a non-empty string")
    if not isinstance(locale, str) or not _LOCALE_RE.match(locale):
        raise CreateBankInvalid(
            "invalid_locale",
            f"locale must match BCP-47 (e.g. 'en' or 'en-US'); got {locale!r}",
        )
    if speaker is not None and not isinstance(speaker, str):
        raise CreateBankInvalid("invalid_speaker", "speaker must be a string or null")
    if not isinstance(inventory_source, str):
        raise CreateBankInvalid(
            "unknown_inventory_source",
            "inventory_source must be a string",
        )

    phonemes = _resolve_inventory(repo_root, seeds_dir, inventory_source)

    bank_path = repo_root / "banks" / bank_id
    if bank_path.exists():
        raise BankIdExists(bank_id)

    new_config: dict = {
        "name": name.strip(),
        "locale": locale,
        "privacy": "private",
        "target_lufs": -16,
        "phonemes": phonemes,
    }
    if speaker and speaker.strip():
        new_config["speaker"] = speaker.strip()

    schema_errors = validate_config(new_config)
    if schema_errors:
        # Defensive: the seed inventory should already be valid; this catches
        # a malformed seed file or a bad copy-from source.
        raise CreateBankInvalid(
            "config_invalid",
            f"assembled config failed validation: {schema_errors}",
        )

    # Best-effort atomicity: create the bank directory first, then write
    # config.json, state.json, and .gitignore. If any write fails, roll
    # back by removing the partially-created directory.
    bank_path.mkdir(parents=True)
    try:
        config_tmp = bank_path / "config.json.tmp"
        config_tmp.write_text(
            json.dumps(new_config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(config_tmp, bank_path / "config.json")
        write_state(bank_path, empty_state())
        sync_gitignore(bank_path, "private")
    except Exception:
        _rollback_bank(bank_path)
        raise

    return {
        "id": bank_id,
        "name": new_config["name"],
        "locale": new_config["locale"],
        "privacy": new_config["privacy"],
        "phoneme_count": len(phonemes),
    }


def _resolve_inventory(
    repo_root: Path, seeds_dir: Path, inventory_source: str
) -> list[dict]:
    if inventory_source == "english-basic":
        return _load_seed_inventory(seeds_dir / "english-basic.json")
    if inventory_source.startswith("copy:"):
        source_id = inventory_source.removeprefix("copy:")
        if not BANK_ID_RE.match(source_id):
            raise CreateBankInvalid(
                "unknown_inventory_source",
                f"copy source {source_id!r} is not a valid bank id",
            )
        source_config_file = repo_root / "banks" / source_id / "config.json"
        if not source_config_file.is_file():
            raise CreateBankInvalid(
                "unknown_inventory_source",
                f"copy source bank {source_id!r} not found",
            )
        try:
            source_cfg = json.loads(source_config_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CreateBankInvalid(
                "unknown_inventory_source",
                f"copy source {source_id!r} has unreadable config: {exc}",
            ) from exc
        phonemes = source_cfg.get("phonemes")
        if not isinstance(phonemes, list) or not phonemes:
            raise CreateBankInvalid(
                "unknown_inventory_source",
                f"copy source {source_id!r} has no phonemes",
            )
        # Deep-ish copy — phoneme entries are flat dicts of scalars.
        return [dict(p) for p in phonemes]
    raise CreateBankInvalid(
        "unknown_inventory_source",
        f"inventory_source must be 'english-basic' or 'copy:<bank-id>'; got {inventory_source!r}",
    )


def _load_seed_inventory(path: Path) -> list[dict]:
    if not path.is_file():
        raise CreateBankInvalid(
            "unknown_inventory_source",
            f"seed inventory missing: {path}",
        )
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CreateBankInvalid(
            "unknown_inventory_source",
            f"seed inventory unreadable: {exc}",
        ) from exc
    phonemes = doc.get("phonemes") if isinstance(doc, dict) else None
    if not isinstance(phonemes, list) or not phonemes:
        raise CreateBankInvalid(
            "unknown_inventory_source",
            f"seed inventory has no phonemes: {path}",
        )
    return [dict(p) for p in phonemes]


def _rollback_bank(bank_path: Path) -> None:
    """Remove a partially-created bank dir so a re-create can succeed."""
    import shutil
    try:
        shutil.rmtree(bank_path)
    except OSError as exc:
        logger.warning("failed to roll back %s: %s", bank_path, exc)
