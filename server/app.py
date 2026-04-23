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
import shutil
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from server.banks import BankInvalid, BankNotFound, list_banks, read_bank

VERSION = "0.1.0"
DEFAULT_PORT = 8766

STATIC_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".map": "application/json",
}


@dataclass
class ServerConfig:
    repo_root: Path
    port: int
    ffmpeg: Path | None
    espeak: Path | None


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
    return ServerConfig(
        repo_root=args.repo_root,
        port=args.port,
        ffmpeg=ffmpeg,
        espeak=espeak,
    )


def main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    missing = []
    if config.ffmpeg is None:
        missing.append("ffmpeg")
    if config.espeak is None:
        missing.append("espeak-ng")
    if missing:
        sys.stderr.write(
            f"warning: missing tools on PATH: {', '.join(missing)}. "
            "Install with: brew install ffmpeg espeak-ng\n"
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
