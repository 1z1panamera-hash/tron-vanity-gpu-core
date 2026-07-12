from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .config import ConfigError, PRODUCTION_PATH_DENYLIST, _bool


@dataclass(frozen=True)
class WorkerSettings:
    environment: str
    worker_id: str
    controller_url: str
    state_db_path: Path
    core_socket_path: Path
    age_recipient: str
    tls_ca_path: Path | None
    tls_cert_path: Path | None
    tls_key_path: Path | None
    allow_insecure_local: bool
    heartbeat_seconds: float
    reconnect_min_seconds: float
    reconnect_max_seconds: float

    @classmethod
    def from_env(cls) -> "WorkerSettings":
        ca = os.environ.get("VANITY18035_CONTROLLER_CA", "").strip()
        cert = os.environ.get("VANITY18035_WORKER_CERT", "").strip()
        key = os.environ.get("VANITY18035_WORKER_KEY", "").strip()
        return cls(
            environment=os.environ.get("VANITY18035_ENV", "development").strip().lower(),
            worker_id=os.environ.get("VANITY18035_WORKER_ID", "").strip(),
            controller_url=os.environ.get("VANITY18035_CONTROLLER_URL", "").strip().rstrip("/"),
            state_db_path=Path(os.environ.get(
                "VANITY18035_WORKER_DB",
                "/var/lib/vanity-api-18035/worker.sqlite3",
            )),
            core_socket_path=Path(os.environ.get(
                "VANITY18035_CORE_SOCKET",
                "/run/vanity-api-18035/core.sock",
            )),
            age_recipient=os.environ.get("VANITY18035_AGE_RECIPIENT", "").strip(),
            tls_ca_path=Path(ca) if ca else None,
            tls_cert_path=Path(cert) if cert else None,
            tls_key_path=Path(key) if key else None,
            allow_insecure_local=_bool("VANITY18035_ALLOW_INSECURE_LOCAL", False),
            heartbeat_seconds=float(os.environ.get("VANITY18035_HEARTBEAT_SECONDS", "1")),
            reconnect_min_seconds=float(os.environ.get("VANITY18035_RECONNECT_MIN", "0.1")),
            reconnect_max_seconds=float(os.environ.get("VANITY18035_RECONNECT_MAX", "5")),
        )

    def validate(self) -> None:
        if len(self.worker_id) < 8:
            raise ConfigError("worker ID is required")
        parsed = urlparse(self.controller_url)
        local = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
        if parsed.scheme != "https" and not (
            self.allow_insecure_local and local and parsed.scheme == "http"
        ):
            raise ConfigError("worker controller URL must use HTTPS")
        if any(value in self.controller_url for value in PRODUCTION_PATH_DENYLIST):
            raise ConfigError("worker controller URL crosses a protected production boundary")
        state_text = str(self.state_db_path.resolve())
        if any(value in state_text for value in PRODUCTION_PATH_DENYLIST):
            raise ConfigError("worker state path crosses a protected production boundary")
        if (self.tls_cert_path is None) != (self.tls_key_path is None):
            raise ConfigError("worker certificate and key must be configured together")
        if self.environment == "production":
            if not self.tls_ca_path or not self.tls_cert_path or not self.tls_key_path:
                raise ConfigError("production worker requires CA, client certificate, and key")
            if not self.age_recipient.startswith("age1"):
                raise ConfigError("production worker requires an Age recipient")
        if self.heartbeat_seconds <= 0 or self.heartbeat_seconds > 5:
            raise ConfigError("heartbeat interval must be in (0, 5] seconds")
        if self.reconnect_min_seconds <= 0 or self.reconnect_max_seconds < self.reconnect_min_seconds:
            raise ConfigError("invalid reconnect bounds")
