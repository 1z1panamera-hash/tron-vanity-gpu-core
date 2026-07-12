from __future__ import annotations

import asyncio
import ssl
import tempfile
import unittest
import uuid
from pathlib import Path

from aiohttp import ClientSession, TCPConnector, web

from vanity18035.api import build_ssl_context, create_app
from vanity18035.core_adapter import EncryptedHit, FakeCoreAdapter
from vanity18035.worker_agent import WorkerAgent
from vanity18035.worker_client import ControllerClient
from vanity18035.worker_state import WorkerState

from .helpers import test_settings
from .test_mtls_api import make_ca, make_certificate
from .test_worker_config import settings as worker_settings


class EndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def test_p0_request_crosses_mtls_worker_and_durable_outbox(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            server_ca_key, server_ca = make_ca(directory, "e2e-server-ca")
            worker_ca_key, worker_ca = make_ca(directory, "e2e-worker-ca")
            server_key, server_certificate = make_certificate(
                directory,
                "e2e-server",
                "127.0.0.1",
                server_ca_key,
                server_ca,
                "subjectAltName=IP:127.0.0.1\nextendedKeyUsage=serverAuth\n",
            )
            worker_key, worker_certificate = make_certificate(
                directory,
                "e2e-worker",
                "worker-0001",
                worker_ca_key,
                worker_ca,
                "extendedKeyUsage=clientAuth\n",
            )
            controller_settings = test_settings(
                directory / "controller.sqlite3",
                environment="production",
                host="0.0.0.0",
                customer_allowed_ips=frozenset({"127.0.0.1"}),
                worker_allowed_ips=frozenset({"127.0.0.1"}),
                callback_url="https://customer.example/callback",
                age_recipient="age1testrecipient",
                tls_cert_path=server_certificate,
                tls_key_path=server_key,
                worker_ca_path=worker_ca,
                require_worker_mtls=True,
            )
            runner = web.AppRunner(create_app(controller_settings))
            await runner.setup()
            site = web.TCPSite(
                runner,
                "127.0.0.1",
                0,
                ssl_context=build_ssl_context(controller_settings),
            )
            await site.start()
            assert site._server is not None
            port = site._server.sockets[0].getsockname()[1]

            state = WorkerState(directory / "worker.sqlite3")
            core = FakeCoreAdapter()
            settings = worker_settings(
                temporary,
                environment="production",
                controller_url=f"https://127.0.0.1:{port}",
                age_recipient="age1testrecipient",
                tls_ca_path=server_ca,
                tls_cert_path=worker_certificate,
                tls_key_path=worker_key,
                allow_insecure_local=False,
                heartbeat_seconds=0.05,
                reconnect_min_seconds=0.01,
                reconnect_max_seconds=0.1,
            )
            agent = WorkerAgent(settings, state, ControllerClient(settings), core)
            agent_task = asyncio.create_task(agent.run())

            customer_context = ssl.create_default_context(cafile=str(server_ca))
            try:
                async with ClientSession(
                    connector=TCPConnector(ssl=customer_context)
                ) as customer:
                    for _ in range(100):
                        health = await customer.get(f"https://127.0.0.1:{port}/health")
                        payload = await health.json()
                        if payload["gpu_worker_healthy"]:
                            break
                        await asyncio.sleep(0.01)
                    else:
                        self.fail("worker did not become healthy")

                    request = asyncio.create_task(
                        customer.post(
                            f"https://127.0.0.1:{port}/v1/find",
                            json={"suffix": "Yqvi2"},
                        )
                    )
                    task = None
                    for _ in range(200):
                        for _, snapshot in core.snapshots:
                            if snapshot:
                                task = snapshot[0]
                        if task is not None:
                            break
                        await asyncio.sleep(0.005)
                    self.assertIsNotNone(task)
                    assert task is not None
                    result_id = str(uuid.uuid4())
                    await core.hits.put(
                        EncryptedHit(
                            result_id=result_id,
                            event_id=str(uuid.uuid4()),
                            item_id=task.item_id,
                            lease_id=task.lease_id,
                            matched_address="T" + "1" * 28 + "Yqvi2",
                            encrypted_private_key=(
                                "-----BEGIN AGE ENCRYPTED FILE-----\n"
                                "test-ciphertext\n"
                                "-----END AGE ENCRYPTED FILE-----\n"
                            ),
                        )
                    )
                    response = await asyncio.wait_for(request, timeout=3)
                    self.assertEqual(response.status, 200, await response.text())
                    body = await response.json()
                    self.assertEqual(body["matched_address"], "T" + "1" * 28 + "Yqvi2")

                    for _ in range(200):
                        if not state.due_results() and core.acked_hits == [result_id]:
                            break
                        await asyncio.sleep(0.005)
                    self.assertEqual(core.acked_hits, [result_id])
                    self.assertEqual(state.due_results(), [])
            finally:
                await agent.stop()
                agent_task.cancel()
                await asyncio.gather(agent_task, return_exceptions=True)
                await runner.cleanup()


if __name__ == "__main__":
    unittest.main()
