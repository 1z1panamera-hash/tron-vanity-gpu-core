from __future__ import annotations

from pathlib import Path

from vanity18035.config import Settings


def test_settings(db_path: Path, **overrides: object) -> Settings:
    values = {
        "environment": "test",
        "host": "127.0.0.1",
        "port": 18035,
        "db_path": db_path,
        "customer_allowed_ips": frozenset(),
        "worker_allowed_ips": frozenset(),
        "worker_id": "worker-0001",
        "callback_url": "",
        "age_recipient": "",
        "tls_cert_path": None,
        "tls_key_path": None,
        "worker_ca_path": None,
        "require_worker_mtls": False,
        "allow_insecure_local": True,
        "p0_max_inflight": 8,
        "p0_hard_timeout_seconds": 10.0,
        "p0_http_timeout_seconds": 15.0,
        "p0_cache_seconds": 60.0,
        "worker_stale_seconds": 5.0,
        "internal_clock_skew_seconds": 30,
    }
    values.update(overrides)
    return Settings(**values)
