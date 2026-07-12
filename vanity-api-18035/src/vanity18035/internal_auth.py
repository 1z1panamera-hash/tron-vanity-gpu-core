from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Mapping

from .config import Settings
from .database import ControllerDatabase


IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
NONCE_RE = re.compile(r"^[A-Fa-f0-9]{32,128}$")


class WorkerAuthError(PermissionError):
    """Raised when a Vast worker request cannot be authenticated."""


@dataclass(frozen=True)
class WorkerIdentity:
    worker_id: str
    event_id: str


class WorkerAuthenticator:
    def __init__(self, settings: Settings, database: ControllerDatabase):
        self.settings = settings
        self.database = database

    def verify(
        self,
        payload: Mapping[str, Any],
        *,
        remote_ip: str | None,
        peer_certificate: Mapping[str, Any] | None,
        now: float | None = None,
    ) -> WorkerIdentity:
        now = time.time() if now is None else now
        if self.settings.worker_allowed_ips and remote_ip not in self.settings.worker_allowed_ips:
            raise WorkerAuthError("worker source IP is not allowed")
        if self.settings.require_worker_mtls and not peer_certificate:
            raise WorkerAuthError("worker client certificate is required")

        worker_id = payload.get("worker_id")
        event_id = payload.get("event_id")
        nonce = payload.get("nonce")
        timestamp = payload.get("timestamp")
        if not isinstance(worker_id, str) or not IDENTIFIER_RE.fullmatch(worker_id):
            raise WorkerAuthError("invalid worker ID")
        if self.settings.worker_id and worker_id != self.settings.worker_id:
            raise WorkerAuthError("unknown worker ID")
        if self.settings.require_worker_mtls:
            common_names = self._certificate_common_names(peer_certificate or {})
            if common_names != {worker_id}:
                raise WorkerAuthError("worker certificate identity does not match worker ID")
        if not isinstance(event_id, str) or not IDENTIFIER_RE.fullmatch(event_id):
            raise WorkerAuthError("invalid event ID")
        if not isinstance(nonce, str) or not NONCE_RE.fullmatch(nonce):
            raise WorkerAuthError("invalid request nonce")
        if not isinstance(timestamp, (int, float)):
            raise WorkerAuthError("invalid request timestamp")
        if abs(now - float(timestamp)) > self.settings.internal_clock_skew_seconds:
            raise WorkerAuthError("worker request timestamp is outside the allowed clock skew")
        if not self.database.register_nonce(
            worker_id,
            nonce,
            retention_seconds=self.settings.internal_clock_skew_seconds * 4,
            now=now,
        ):
            raise WorkerAuthError("worker request nonce was already used")
        return WorkerIdentity(worker_id=worker_id, event_id=event_id)

    @staticmethod
    def _certificate_common_names(certificate: Mapping[str, Any]) -> set[str]:
        result: set[str] = set()
        subject = certificate.get("subject", ())
        if not isinstance(subject, (tuple, list)):
            return result
        for relative_name in subject:
            if not isinstance(relative_name, (tuple, list)):
                continue
            for attribute in relative_name:
                if (
                    isinstance(attribute, (tuple, list))
                    and len(attribute) == 2
                    and attribute[0] == "commonName"
                    and isinstance(attribute[1], str)
                ):
                    result.add(attribute[1])
        return result
