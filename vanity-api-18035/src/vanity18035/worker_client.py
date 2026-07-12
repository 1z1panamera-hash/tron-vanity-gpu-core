from __future__ import annotations

import ssl
import time
import uuid
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .worker_config import WorkerSettings


class ControllerClientError(RuntimeError):
    pass


class ControllerClient:
    def __init__(self, settings: WorkerSettings):
        self.settings = settings
        self._session: ClientSession | None = None

    async def start(self) -> None:
        self._session = ClientSession(
            timeout=ClientTimeout(total=30),
            connector=None,
        )

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def ssl_context(self) -> ssl.SSLContext | bool:
        if self.settings.controller_url.startswith("http://"):
            return False
        context = ssl.create_default_context(cafile=str(self.settings.tls_ca_path))
        assert self.settings.tls_cert_path is not None
        assert self.settings.tls_key_path is not None
        context.load_cert_chain(self.settings.tls_cert_path, self.settings.tls_key_path)
        return context

    def metadata(self) -> dict[str, Any]:
        return {
            "worker_id": self.settings.worker_id,
            "event_id": str(uuid.uuid4()),
            "nonce": uuid.uuid4().hex,
            "timestamp": time.time(),
        }

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._session is None:
            raise ControllerClientError("controller client is not started")
        body = self.metadata()
        body.update(payload)
        async with self._session.post(
            self.settings.controller_url + path,
            json=body,
            ssl=self.ssl_context(),
            allow_redirects=False,
        ) as response:
            data = await response.json()
            if response.status < 200 or response.status >= 300:
                raise ControllerClientError(f"controller returned HTTP {response.status}")
            if not isinstance(data, dict):
                raise ControllerClientError("controller response is not an object")
            return data
