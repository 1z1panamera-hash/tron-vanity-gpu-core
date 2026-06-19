#!/usr/bin/env python3
"""Minimal local HTTP backend for Vast Serverless PyWorker.

The server keeps the existing app.handler contract and does not log request or
response bodies, because find responses may contain age ciphertext.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import app


HOST = os.environ.get("VAST_MODEL_SERVER_HOST", "127.0.0.1")
PORT = int(os.environ.get("VAST_MODEL_SERVER_PORT", "18000"))
LOG_PATH = Path(os.environ.get("VAST_MODEL_LOG_FILE", "/var/log/tron-vanity/model.log"))


def write_log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fp:
        fp.write(message.rstrip() + "\n")
    print(message, flush=True)


class VanityHandler(BaseHTTPRequestHandler):
    server_version = "tron-vanity-vast/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003 - stdlib API name.
        write_log(f"request {self.command} {self.path} {fmt % args}")

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("request body must be a JSON object")
        return parsed

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API.
        if self.path.rstrip("/") in {"", "/health"}:
            self._write_json(200, app.handler({"input": {"mode": "health"}}))
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API.
        try:
            body = self._read_json_body()
            if self.path.rstrip("/") == "/health":
                payload = {"mode": "health"}
            elif self.path.rstrip("/") == "/find":
                payload = body.get("input", body)
                if not isinstance(payload, dict):
                    raise ValueError("input must be an object")
                payload = dict(payload)
                payload.setdefault("mode", "find")
            else:
                self._write_json(404, {"error": "not found"})
                return

            result = app.handler({"input": payload})
            status = 200 if not result.get("error") else 500
            self._write_json(status, result)
        except Exception as exc:  # noqa: BLE001 - convert backend errors to JSON.
            self._write_json(
                500,
                {
                    "error": str(exc),
                    "notes": ["No key material or credential material is returned by this error path."],
                },
            )


def main() -> int:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_log("Application startup complete.")
    server = ThreadingHTTPServer((HOST, PORT), VanityHandler)
    write_log(f"Vast model backend listening on {HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        write_log("Vast model backend stopping.")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
