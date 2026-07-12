from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


PRODUCTION_PATH_DENYLIST = (
    "/opt/vanity-address-api",
    "18030",
    "18031",
    "18032",
)


class ConfigError(ValueError):
    """Raised when a configuration could cross a production boundary."""


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _ip_set(raw: str) -> frozenset[str]:
    result: set[str] = set()
    for value in raw.split(","):
        value = value.strip()
        if value:
            result.add(str(ipaddress.ip_address(value)))
    return frozenset(result)


@dataclass(frozen=True)
class Settings:
    environment: str
    host: str
    port: int
    db_path: Path
    customer_allowed_ips: frozenset[str]
    worker_allowed_ips: frozenset[str]
    worker_id: str
    callback_url: str
    age_recipient: str
    tls_cert_path: Path | None
    tls_key_path: Path | None
    worker_ca_path: Path | None
    require_worker_mtls: bool
    allow_insecure_local: bool
    p0_max_inflight: int
    p0_hard_timeout_seconds: float
    p0_http_timeout_seconds: float
    p0_cache_seconds: float
    worker_stale_seconds: float
    internal_clock_skew_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        cert = os.environ.get("VANITY18035_TLS_CERT", "").strip()
        key = os.environ.get("VANITY18035_TLS_KEY", "").strip()
        ca = os.environ.get("VANITY18035_WORKER_CA", "").strip()
        return cls(
            environment=os.environ.get("VANITY18035_ENV", "development").strip().lower(),
            host=os.environ.get("VANITY18035_HOST", "127.0.0.1").strip(),
            port=int(os.environ.get("VANITY18035_PORT", "18035")),
            db_path=Path(os.environ.get(
                "VANITY18035_DB",
                "/opt/vanity-api-18035/data/controller.sqlite3",
            )),
            customer_allowed_ips=_ip_set(os.environ.get("VANITY18035_CUSTOMER_IPS", "")),
            worker_allowed_ips=_ip_set(os.environ.get("VANITY18035_WORKER_IPS", "")),
            worker_id=os.environ.get("VANITY18035_WORKER_ID", "").strip(),
            callback_url=os.environ.get("VANITY18035_CALLBACK_URL", "").strip(),
            age_recipient=os.environ.get("VANITY18035_AGE_RECIPIENT", "").strip(),
            tls_cert_path=Path(cert) if cert else None,
            tls_key_path=Path(key) if key else None,
            worker_ca_path=Path(ca) if ca else None,
            require_worker_mtls=_bool("VANITY18035_REQUIRE_WORKER_MTLS", True),
            allow_insecure_local=_bool("VANITY18035_ALLOW_INSECURE_LOCAL", False),
            p0_max_inflight=int(os.environ.get("VANITY18035_P0_MAX_INFLIGHT", "8")),
            p0_hard_timeout_seconds=float(os.environ.get("VANITY18035_P0_HARD_TIMEOUT", "10")),
            p0_http_timeout_seconds=float(os.environ.get("VANITY18035_P0_HTTP_TIMEOUT", "15")),
            p0_cache_seconds=float(os.environ.get("VANITY18035_P0_CACHE_SECONDS", "60")),
            worker_stale_seconds=float(os.environ.get("VANITY18035_WORKER_STALE_SECONDS", "5")),
            internal_clock_skew_seconds=int(os.environ.get("VANITY18035_CLOCK_SKEW_SECONDS", "30")),
        )

    def validate(self) -> None:
        if self.port != 18035:
            raise ConfigError("the customer service must use port 18035")
        if self.p0_max_inflight < 1 or self.p0_max_inflight > 8:
            raise ConfigError("P0 max inflight must be between 1 and 8")
        if self.p0_hard_timeout_seconds <= 0:
            raise ConfigError("P0 hard timeout must be positive")
        if self.p0_http_timeout_seconds <= self.p0_hard_timeout_seconds:
            raise ConfigError("P0 HTTP timeout must exceed the GPU hard timeout")
        if self.p0_cache_seconds < 0:
            raise ConfigError("P0 cache seconds cannot be negative")

        db_text = str(self.db_path.resolve())
        if any(value in db_text for value in PRODUCTION_PATH_DENYLIST):
            raise ConfigError("18035 database path crosses a protected production boundary")

        is_loopback = self.host in {"127.0.0.1", "::1", "localhost"}
        tls_complete = self.tls_cert_path is not None and self.tls_key_path is not None
        if (self.tls_cert_path is None) != (self.tls_key_path is None):
            raise ConfigError("TLS certificate and key must be configured together")
        if not tls_complete and not (self.allow_insecure_local and is_loopback):
            raise ConfigError("TLS is required except for explicitly enabled loopback tests")

        if self.environment == "production":
            if is_loopback:
                raise ConfigError("production must listen on a non-loopback address")
            if not self.customer_allowed_ips:
                raise ConfigError("production requires a customer IPv4 allowlist")
            if not self.worker_allowed_ips:
                raise ConfigError("production requires a Vast worker IPv4 allowlist")
            if len(self.worker_id) < 8:
                raise ConfigError("production requires the expected Vast worker ID")
            if not self.require_worker_mtls or self.worker_ca_path is None:
                raise ConfigError("production internal routes require mTLS and a worker CA")
            if not self.callback_url or urlparse(self.callback_url).scheme != "https":
                raise ConfigError("production callback URL must use HTTPS")
            if not self.age_recipient.startswith("age1"):
                raise ConfigError("production requires a configured Age recipient")
