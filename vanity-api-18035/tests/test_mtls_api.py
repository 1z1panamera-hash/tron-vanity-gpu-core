from __future__ import annotations

import os
import ssl
import subprocess
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from aiohttp import ClientSession, TCPConnector, web

from vanity18035.api import build_ssl_context, create_app

from .helpers import test_settings


def run_openssl(*arguments: str) -> None:
    subprocess.run(
        ["openssl", *arguments],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def make_ca(directory: Path, name: str) -> tuple[Path, Path]:
    key = directory / f"{name}.key"
    certificate = directory / f"{name}.crt"
    run_openssl(
        "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-subj", f"/CN={name}", "-keyout", str(key), "-out", str(certificate),
    )
    os.chmod(key, 0o600)
    return key, certificate


def make_certificate(
    directory: Path,
    name: str,
    common_name: str,
    ca_key: Path,
    ca_certificate: Path,
    extensions: str | None = None,
) -> tuple[Path, Path]:
    key = directory / f"{name}.key"
    request = directory / f"{name}.csr"
    certificate = directory / f"{name}.crt"
    run_openssl(
        "req", "-newkey", "rsa:2048", "-nodes", "-subj", f"/CN={common_name}",
        "-keyout", str(key), "-out", str(request),
    )
    command = [
        "x509", "-req", "-days", "1", "-in", str(request),
        "-CA", str(ca_certificate), "-CAkey", str(ca_key), "-CAcreateserial",
        "-out", str(certificate),
    ]
    if extensions is not None:
        extension_file = directory / f"{name}.ext"
        extension_file.write_text(extensions, encoding="ascii")
        command.extend(["-extfile", str(extension_file)])
    run_openssl(*command)
    os.chmod(key, 0o600)
    return key, certificate


class MtlsApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        directory = Path(self.temp.name)
        server_ca_key, self.server_ca = make_ca(directory, "server-test-ca")
        worker_ca_key, self.worker_ca = make_ca(directory, "worker-test-ca")
        self.server_key, self.server_certificate = make_certificate(
            directory,
            "server",
            "127.0.0.1",
            server_ca_key,
            self.server_ca,
            "subjectAltName=IP:127.0.0.1\nextendedKeyUsage=serverAuth\n",
        )
        self.worker_key, self.worker_certificate = make_certificate(
            directory,
            "worker",
            "worker-0001",
            worker_ca_key,
            self.worker_ca,
            "extendedKeyUsage=clientAuth\n",
        )
        self.other_key, self.other_certificate = make_certificate(
            directory,
            "other-worker",
            "worker-0002",
            worker_ca_key,
            self.worker_ca,
            "extendedKeyUsage=clientAuth\n",
        )
        settings = test_settings(
            directory / "controller.sqlite3",
            environment="production",
            host="0.0.0.0",
            customer_allowed_ips=frozenset({"127.0.0.1"}),
            worker_allowed_ips=frozenset({"127.0.0.1"}),
            callback_url="https://customer.example/callback",
            age_recipient="age1testrecipient",
            tls_cert_path=self.server_certificate,
            tls_key_path=self.server_key,
            worker_ca_path=self.worker_ca,
            require_worker_mtls=True,
        )
        self.runner = web.AppRunner(create_app(settings))
        await self.runner.setup()
        self.site = web.TCPSite(
            self.runner,
            "127.0.0.1",
            0,
            ssl_context=build_ssl_context(settings),
        )
        await self.site.start()
        assert self.site._server is not None
        port = self.site._server.sockets[0].getsockname()[1]
        self.url = f"https://127.0.0.1:{port}"

    async def asyncTearDown(self) -> None:
        await self.runner.cleanup()
        self.temp.cleanup()

    def client_context(
        self,
        certificate: Path | None = None,
        key: Path | None = None,
    ) -> ssl.SSLContext:
        context = ssl.create_default_context(cafile=str(self.server_ca))
        if certificate is not None and key is not None:
            context.load_cert_chain(certificate, key)
        return context

    @staticmethod
    def worker_payload() -> dict[str, object]:
        return {
            "worker_id": "worker-0001",
            "event_id": str(uuid.uuid4()),
            "nonce": uuid.uuid4().hex,
            "timestamp": time.time(),
            "status": "healthy",
            "capabilities": {"gpu": "test"},
            "progress": [],
        }

    async def post_heartbeat(self, context: ssl.SSLContext) -> int:
        async with ClientSession(connector=TCPConnector(ssl=context)) as session:
            response = await session.post(
                self.url + "/internal/v1/worker/heartbeat",
                json=self.worker_payload(),
            )
            await response.read()
            return response.status

    async def test_customer_route_allows_no_client_certificate(self) -> None:
        async with ClientSession(
            connector=TCPConnector(ssl=self.client_context())
        ) as session:
            response = await session.get(self.url + "/health")
            self.assertEqual(response.status, 200)

    async def test_internal_route_requires_matching_worker_certificate(self) -> None:
        self.assertEqual(await self.post_heartbeat(self.client_context()), 403)
        self.assertEqual(
            await self.post_heartbeat(
                self.client_context(self.other_certificate, self.other_key)
            ),
            403,
        )
        self.assertEqual(
            await self.post_heartbeat(
                self.client_context(self.worker_certificate, self.worker_key)
            ),
            200,
        )


if __name__ == "__main__":
    unittest.main()
