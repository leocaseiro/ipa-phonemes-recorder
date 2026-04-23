# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""HTTP server for the IPA phonemes recorder."""

from __future__ import annotations

import sys

if sys.version_info < (3, 10):
    sys.stderr.write(
        f"ipa-phonemes-recorder requires Python 3.10+, got {sys.version.split()[0]}. "
        f"Try: python3.11 -m server.app\n"
    )
    raise SystemExit(1)

import argparse
import json
import re
import shutil
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from server.banks import BankInvalid, BankNotFound, list_banks, read_bank
from server.references import (
    ReferenceError,
    load_phoneme_reference_files,
    serve_reference,
)
from server.state import validate_state_shape, write_state
from server.takes import (
    TakeNotFound,
    TakeSaveFailed,
    delete_take,
    get_take_wav_path,
    save_take,
)

VERSION = "0.1.0"
DEFAULT_PORT = 8766

STATIC_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".map": "application/json",
}

UPLOAD_CONTENT_TYPES = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
}

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_STATE_BYTES = 10 * 1024 * 1024

TAKE_POST_RE = re.compile(r"^/api/banks/([^/]+)/phonemes/([^/]+)/takes$")
TAKE_FILE_RE = re.compile(r"^/api/banks/([^/]+)/phonemes/([^/]+)/takes/([^/]+)$")
REFERENCE_GET_RE = re.compile(r"^/api/banks/([^/]+)/phonemes/([^/]+)/reference$")
STATE_PUT_RE = re.compile(r"^/api/banks/([^/]+)/state$")


@dataclass
class ServerConfig:
    repo_root: Path
    port: int
    ffmpeg: Path | None
    espeak: Path | None
    phoneme_reference_files: dict[str, str]


def probe_tools() -> tuple[Path | None, Path | None]:
    def _which(name: str) -> Path | None:
        found = shutil.which(name)
        return Path(found) if found else None

    return _which("ffmpeg"), _which("espeak-ng")


class AppRequestHandler(BaseHTTPRequestHandler):
    server_version = f"ipa-phonemes-recorder/{VERSION}"

    @property
    def config(self) -> ServerConfig:
        return self.server.config  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                self._send_health()
            elif path == "/api/banks":
                self._list_banks()
            elif (match := TAKE_FILE_RE.match(path)):
                bank_id, phoneme_id, take_id = match.groups()
                self._serve_take_wav(bank_id, phoneme_id, take_id)
            elif (match := REFERENCE_GET_RE.match(path)):
                bank_id, phoneme_id = match.groups()
                self._serve_reference(bank_id, phoneme_id)
            elif path.startswith("/api/banks/"):
                remainder = path.removeprefix("/api/banks/")
                if remainder and "/" not in remainder:
                    self._read_bank(remainder)
                else:
                    self._send_json(
                        HTTPStatus.NOT_FOUND,
                        {"error": "not_found", "message": f"No route for {self.path}"},
                    )
            elif path == "/":
                self._serve_static("index.html")
            elif path.startswith("/ui/"):
                self._serve_static(path.removeprefix("/ui/"))
            else:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    {"error": "not_found", "message": f"No route for {self.path}"},
                )
        except Exception as exc:  # pragma: no cover - defensive
            self.log_error("handler crashed: %s", exc)
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "internal_error", "message": str(exc)},
            )

    def do_DELETE(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            match = TAKE_FILE_RE.match(path)
            if match:
                self._delete_take(*match.groups())
            else:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    {"error": "not_found", "message": f"No route for DELETE {self.path}"},
                )
        except Exception as exc:  # pragma: no cover - defensive
            self.log_error("handler crashed: %s", exc)
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "internal_error", "message": str(exc)},
            )

    def do_PUT(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            match = STATE_PUT_RE.match(path)
            if match:
                self._put_state(match.group(1))
            else:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    {"error": "not_found", "message": f"No route for PUT {self.path}"},
                )
        except Exception as exc:  # pragma: no cover - defensive
            self.log_error("handler crashed: %s", exc)
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "internal_error", "message": str(exc)},
            )

    def do_POST(self) -> None:  # noqa: N802 (stdlib naming)
        path = urlparse(self.path).path
        try:
            match = TAKE_POST_RE.match(path)
            if match:
                bank_id, phoneme_id = match.groups()
                self._create_take(bank_id, phoneme_id)
            else:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    {"error": "not_found", "message": f"No route for POST {self.path}"},
                )
        except Exception as exc:  # pragma: no cover - defensive
            self.log_error("handler crashed: %s", exc)
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "internal_error", "message": str(exc)},
            )

    def _create_take(self, bank_id: str, phoneme_id: str) -> None:
        try:
            bank = read_bank(self.config.repo_root, bank_id)
        except BankNotFound:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found", "message": f"bank {bank_id!r} not found"},
            )
            return
        except BankInvalid as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "bank_invalid", "errors": exc.errors},
            )
            return

        phoneme_ids = {p["id"] for p in bank["config"]["phonemes"]}
        if phoneme_id not in phoneme_ids:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {
                    "error": "not_found",
                    "message": f"phoneme {phoneme_id!r} not in bank {bank_id!r}",
                },
            )
            return

        raw_type = self.headers.get("Content-Type", "")
        content_type = raw_type.split(";")[0].strip().lower()
        src_ext = UPLOAD_CONTENT_TYPES.get(content_type)
        if not src_ext:
            self._send_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {
                    "error": "unsupported_media_type",
                    "message": (
                        f"Content-Type {content_type!r} not supported; "
                        f"expected one of {sorted(UPLOAD_CONTENT_TYPES)}"
                    ),
                },
            )
            return

        length_header = self.headers.get("Content-Length")
        if not length_header:
            self._send_json(
                HTTPStatus.LENGTH_REQUIRED,
                {"error": "length_required", "message": "Content-Length header is required"},
            )
            return
        try:
            length = int(length_header)
        except ValueError:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "bad_request", "message": "invalid Content-Length"},
            )
            return
        if length <= 0:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "bad_request", "message": "empty body"},
            )
            return
        if length > MAX_UPLOAD_BYTES:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {
                    "error": "payload_too_large",
                    "message": f"body size {length} exceeds limit {MAX_UPLOAD_BYTES}",
                },
            )
            return

        if self.config.ffmpeg is None:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "ffmpeg_unavailable",
                    "message": "ffmpeg not found on PATH; install via brew install ffmpeg",
                },
            )
            return

        body = self.rfile.read(length)

        try:
            meta = save_take(
                bank_path=self.config.repo_root / "banks" / bank_id,
                phoneme_id=phoneme_id,
                src_bytes=body,
                src_ext=src_ext,
                ffmpeg=self.config.ffmpeg,
                tmp_root=self.config.repo_root / "tmp",
            )
        except TakeSaveFailed as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": exc.code,
                    "message": exc.message,
                    "detail": exc.detail,
                    "tmp_path": str(exc.tmp_path) if exc.tmp_path else None,
                },
            )
            return

        self._send_json(HTTPStatus.CREATED, asdict(meta))

    def _serve_take_wav(self, bank_id: str, phoneme_id: str, take_id: str) -> None:
        try:
            read_bank(self.config.repo_root, bank_id)
        except BankNotFound:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found", "message": f"bank {bank_id!r} not found"},
            )
            return
        except BankInvalid as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "bank_invalid", "errors": exc.errors},
            )
            return
        try:
            wav_path = get_take_wav_path(
                self.config.repo_root / "banks" / bank_id, phoneme_id, take_id
            )
        except TakeNotFound:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {
                    "error": "not_found",
                    "message": f"take {phoneme_id}/{take_id} not found",
                },
            )
            return
        body = wav_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _delete_take(self, bank_id: str, phoneme_id: str, take_id: str) -> None:
        try:
            read_bank(self.config.repo_root, bank_id)
        except BankNotFound:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found", "message": f"bank {bank_id!r} not found"},
            )
            return
        except BankInvalid as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "bank_invalid", "errors": exc.errors},
            )
            return
        try:
            delete_take(
                bank_path=self.config.repo_root / "banks" / bank_id,
                phoneme_id=phoneme_id,
                take_id=take_id,
            )
        except TakeNotFound:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {
                    "error": "not_found",
                    "message": f"take {phoneme_id}/{take_id} not found",
                },
            )
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def _put_state(self, bank_id: str) -> None:
        try:
            read_bank(self.config.repo_root, bank_id)
        except BankNotFound:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found", "message": f"bank {bank_id!r} not found"},
            )
            return
        except BankInvalid as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "bank_invalid", "errors": exc.errors},
            )
            return

        length_header = self.headers.get("Content-Length")
        if not length_header:
            self._send_json(
                HTTPStatus.LENGTH_REQUIRED,
                {"error": "length_required", "message": "Content-Length header is required"},
            )
            return
        try:
            length = int(length_header)
        except ValueError:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "bad_request", "message": "invalid Content-Length"},
            )
            return
        if length > MAX_STATE_BYTES:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": "payload_too_large", "message": f"state size {length} > {MAX_STATE_BYTES}"},
            )
            return

        body = self.rfile.read(length)
        try:
            new_state = json.loads(body)
        except json.JSONDecodeError as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "bad_json", "message": str(exc)},
            )
            return

        errors = validate_state_shape(new_state)
        if errors:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "state_invalid", "errors": errors},
            )
            return

        write_state(self.config.repo_root / "banks" / bank_id, new_state)
        self._send_json(HTTPStatus.OK, new_state)

    def _serve_reference(self, bank_id: str, phoneme_id: str) -> None:
        try:
            bank = read_bank(self.config.repo_root, bank_id)
        except BankNotFound:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found", "message": f"bank {bank_id!r} not found"},
            )
            return
        except BankInvalid as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "bank_invalid", "errors": exc.errors},
            )
            return

        phoneme = next(
            (p for p in bank["config"]["phonemes"] if p.get("id") == phoneme_id),
            None,
        )
        if phoneme is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {
                    "error": "not_found",
                    "message": f"phoneme {phoneme_id!r} not in bank {bank_id!r}",
                },
            )
            return

        refs_root = self.config.repo_root / "references"
        attribution_path = refs_root / "ATTRIBUTION.md"

        try:
            response = serve_reference(
                phoneme=phoneme,
                references_root=refs_root,
                phoneme_reference_files=self.config.phoneme_reference_files,
                attribution_path=attribution_path,
            )
        except ReferenceError as exc:
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"error": exc.code, "message": exc.message},
            )
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        self.send_header("X-Reference-Source", response.source)
        if response.attribution:
            self.send_header("X-Reference-Attribution", response.attribution)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(response.body)

    def _send_health(self) -> None:
        payload = {
            "ok": True,
            "tools": {
                "ffmpeg": self.config.ffmpeg is not None,
                "espeak_ng": self.config.espeak is not None,
            },
            "version": VERSION,
        }
        self._send_json(HTTPStatus.OK, payload)

    def _list_banks(self) -> None:
        self._send_json(
            HTTPStatus.OK,
            {"banks": list_banks(self.config.repo_root)},
        )

    def _read_bank(self, bank_id: str) -> None:
        try:
            bank = read_bank(self.config.repo_root, bank_id)
        except BankNotFound:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found", "message": f"bank {bank_id!r} not found"},
            )
            return
        except BankInvalid as exc:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {
                    "error": "bank_invalid",
                    "message": f"bank {bank_id!r} has invalid config",
                    "errors": exc.errors,
                },
            )
            return
        self._send_json(HTTPStatus.OK, bank)

    def _serve_static(self, rel: str) -> None:
        ext = Path(rel).suffix
        if ext not in STATIC_CONTENT_TYPES:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found", "message": f"Unsupported static extension: {ext!r}"},
            )
            return

        ui_root = (self.config.repo_root / "ui").resolve()
        target = (ui_root / rel).resolve()
        if not target.is_relative_to(ui_root):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "bad_path", "message": "Path escapes ui root"},
            )
            return
        if not target.is_file():
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found", "message": f"No such file: {rel}"},
            )
            return

        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", STATIC_CONTENT_TYPES[ext])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        sys.stderr.write(
            "%s [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args)
        )


def build_server(config: ServerConfig) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", config.port), AppRequestHandler)
    server.config = config  # type: ignore[attr-defined]
    return server


def parse_args(argv: list[str] | None = None) -> ServerConfig:
    parser = argparse.ArgumentParser(description="IPA phonemes recorder server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)
    ffmpeg, espeak = probe_tools()
    seeds = args.repo_root / "server" / "seeds"
    phoneme_reference_files = load_phoneme_reference_files(seeds)
    return ServerConfig(
        repo_root=args.repo_root,
        port=args.port,
        ffmpeg=ffmpeg,
        espeak=espeak,
        phoneme_reference_files=phoneme_reference_files,
    )


def main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    if config.ffmpeg is None:
        sys.stderr.write(
            "warning: ffmpeg not on PATH; recording/convert will fail. "
            "Install with: brew install ffmpeg\n"
        )

    server = build_server(config)
    sys.stderr.write(f"ipa-phonemes-recorder listening on http://127.0.0.1:{config.port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\nshutting down\n")
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
