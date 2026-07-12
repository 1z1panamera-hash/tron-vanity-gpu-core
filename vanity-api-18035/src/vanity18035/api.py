from __future__ import annotations

import asyncio
import json
import ssl
from typing import Any

from aiohttp import ClientSession, ClientTimeout, web

from .callbacks import CallbackDispatcher
from .config import Settings
from .controller import (
    Controller,
    GPUUnavailableError,
    P0BusyError,
    P0TimeoutError,
    ResultValidationError,
)
from .database import ControllerDatabase, DatabaseError
from .internal_auth import WorkerAuthError, WorkerAuthenticator
from .patterns import PatternError, TaskClass, pattern_from_mapping


MAX_JSON_BYTES = 1024 * 1024
SETTINGS_KEY = web.AppKey("settings", Settings)
DATABASE_KEY = web.AppKey("database", ControllerDatabase)
CONTROLLER_KEY = web.AppKey("controller", Controller)
WORKER_AUTH_KEY = web.AppKey("worker_auth", WorkerAuthenticator)
CALLBACK_SESSION_KEY = web.AppKey("callback_session", ClientSession)
CALLBACKS_KEY = web.AppKey("callbacks", CallbackDispatcher)


def _json_error(status: int, code: str, message: str) -> web.Response:
    return web.json_response({"status": "error", "error": code, "message": message}, status=status)


async def _read_object(request: web.Request) -> dict[str, Any]:
    if request.content_length is not None and request.content_length > MAX_JSON_BYTES:
        raise PatternError("request body is too large")
    try:
        value = await request.json(loads=json.loads)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise PatternError("request body is not valid JSON") from error
    if not isinstance(value, dict):
        raise PatternError("request body must be a JSON object")
    return value


def _peer_certificate(request: web.Request) -> dict[str, Any] | None:
    transport = request.transport
    if transport is None:
        return None
    certificate = transport.get_extra_info("peercert")
    return certificate if isinstance(certificate, dict) else None


@web.middleware
async def customer_ip_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
    settings = request.app[SETTINGS_KEY]
    if request.path.startswith("/v1/") and settings.customer_allowed_ips:
        if request.remote not in settings.customer_allowed_ips:
            return _json_error(403, "SOURCE_IP_DENIED", "source IP is not allowed")
    return await handler(request)


async def find(request: web.Request) -> web.Response:
    controller = request.app[CONTROLLER_KEY]
    try:
        payload = await _read_object(request)
        if "items" in payload:
            if set(payload) != {"items"}:
                raise PatternError("batch requests may contain only items")
            raw_items = payload["items"]
            if not isinstance(raw_items, list) or not raw_items or len(raw_items) > 1000:
                raise PatternError("items must contain between 1 and 1000 patterns")
            patterns = []
            for raw in raw_items:
                if not isinstance(raw, dict):
                    raise PatternError("each batch item must be an object")
                pattern = pattern_from_mapping(raw)
                if pattern.task_class == TaskClass.P0:
                    raise PatternError("P0 must be submitted as a single request")
                patterns.append(pattern)
            return web.json_response(await controller.submit_background(patterns))

        pattern = pattern_from_mapping(payload)
        if pattern.task_class == TaskClass.P0:
            return web.json_response(await controller.submit_p0(pattern))
        return web.json_response(await controller.submit_background([pattern]))
    except PatternError as error:
        return _json_error(400, "INVALID_PATTERN", str(error))
    except P0BusyError:
        return _json_error(429, "P0_BUSY", "P0 concurrency limit reached")
    except GPUUnavailableError:
        return _json_error(503, "GPU_UNAVAILABLE", "GPU worker is unavailable")
    except P0TimeoutError:
        return _json_error(504, "P0_TIMEOUT", "P0 task exceeded its time limit")
    except DatabaseError:
        return _json_error(503, "CONTROLLER_UNAVAILABLE", "controller state is unavailable")


async def health(request: web.Request) -> web.Response:
    controller = request.app[CONTROLLER_KEY]
    settings = request.app[SETTINGS_KEY]
    return web.json_response(
        {
            "status": "ok",
            "service": "vanity-api-18035",
            "gpu_worker_healthy": controller.database.worker_is_healthy(settings.worker_stale_seconds),
        }
    )


async def worker_control(request: web.Request) -> web.Response:
    app = request.app
    try:
        payload = await _read_object(request)
        identity = app[WORKER_AUTH_KEY].verify(
            payload,
            remote_ip=request.remote,
            peer_certificate=_peer_certificate(request),
        )
        capabilities = payload.get("capabilities", {})
        if not isinstance(capabilities, dict):
            raise WorkerAuthError("worker capabilities must be an object")
        since_revision = int(payload.get("since_revision", -1))
        wait_seconds = float(payload.get("wait_seconds", 20))
        snapshot = await app[CONTROLLER_KEY].wait_for_control_snapshot(
            identity.worker_id,
            since_revision,
            wait_seconds,
        )
        return web.json_response(snapshot)
    except WorkerAuthError as error:
        return _json_error(403, "WORKER_AUTH_FAILED", str(error))
    except (PatternError, ValueError, TypeError):
        return _json_error(400, "INVALID_WORKER_REQUEST", "invalid worker control request")


async def worker_heartbeat(request: web.Request) -> web.Response:
    app = request.app
    try:
        payload = await _read_object(request)
        identity = app[WORKER_AUTH_KEY].verify(
            payload,
            remote_ip=request.remote,
            peer_certificate=_peer_certificate(request),
        )
        capabilities = payload.get("capabilities", {})
        updates = payload.get("progress", [])
        if not isinstance(capabilities, dict) or not isinstance(updates, list):
            raise WorkerAuthError("invalid heartbeat payload")
        status = str(payload.get("status", "unhealthy"))
        if status not in {"healthy", "unhealthy", "degraded"}:
            raise WorkerAuthError("invalid worker status")
        app[DATABASE_KEY].record_worker(
            identity.worker_id,
            status,
            capabilities,
            str(payload["error_code"]) if payload.get("error_code") else None,
        )
        app[DATABASE_KEY].update_progress(identity.worker_id, updates)
        return web.json_response({"ack": True, "revision": app[DATABASE_KEY].revision()})
    except WorkerAuthError as error:
        return _json_error(403, "WORKER_AUTH_FAILED", str(error))
    except (KeyError, ValueError, TypeError, DatabaseError):
        return _json_error(400, "INVALID_WORKER_REQUEST", "invalid worker heartbeat")


async def worker_result(request: web.Request) -> web.Response:
    app = request.app
    try:
        payload = await _read_object(request)
        identity = app[WORKER_AUTH_KEY].verify(
            payload,
            remote_ip=request.remote,
            peer_certificate=_peer_certificate(request),
        )
        response = await app[CONTROLLER_KEY].accept_result(
            worker_id=identity.worker_id,
            event_id=identity.event_id,
            payload=payload,
        )
        return web.json_response(response)
    except WorkerAuthError as error:
        return _json_error(403, "WORKER_AUTH_FAILED", str(error))
    except (ResultValidationError, DatabaseError) as error:
        return _json_error(400, "INVALID_RESULT", str(error))


async def _startup(app: web.Application) -> None:
    await app[CONTROLLER_KEY].start()
    callback_session = ClientSession(timeout=ClientTimeout(total=5))

    async def callback_sender(url: str, payload: dict[str, object]) -> bool:
        async with callback_session.post(url, json=payload, allow_redirects=False) as response:
            await response.read()
            return 200 <= response.status < 300

    callbacks = CallbackDispatcher(app[SETTINGS_KEY], app[DATABASE_KEY], callback_sender)
    app[CALLBACK_SESSION_KEY] = callback_session
    app[CALLBACKS_KEY] = callbacks
    await callbacks.start()


async def _cleanup(app: web.Application) -> None:
    callbacks = app.get(CALLBACKS_KEY)
    if callbacks is not None:
        await callbacks.stop()
    await app[CONTROLLER_KEY].stop()
    callback_session = app.get(CALLBACK_SESSION_KEY)
    if callback_session is not None:
        await callback_session.close()


def create_app(settings: Settings) -> web.Application:
    settings.validate()
    database = ControllerDatabase(settings.db_path)
    controller = Controller(settings, database)

    app = web.Application(middlewares=[customer_ip_middleware], client_max_size=MAX_JSON_BYTES)
    app[SETTINGS_KEY] = settings
    app[DATABASE_KEY] = database
    app[CONTROLLER_KEY] = controller
    app[WORKER_AUTH_KEY] = WorkerAuthenticator(settings, database)
    app.router.add_get("/health", health)
    app.router.add_post("/v1/find", find)
    app.router.add_post("/internal/v1/worker/control", worker_control)
    app.router.add_post("/internal/v1/worker/heartbeat", worker_heartbeat)
    app.router.add_post("/internal/v1/worker/result", worker_result)
    app.on_startup.append(_startup)
    app.on_cleanup.append(_cleanup)
    return app


def build_ssl_context(settings: Settings) -> ssl.SSLContext | None:
    if settings.tls_cert_path is None or settings.tls_key_path is None:
        return None
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(settings.tls_cert_path, settings.tls_key_path)
    if settings.worker_ca_path:
        context.load_verify_locations(settings.worker_ca_path)
        context.verify_mode = ssl.CERT_OPTIONAL
    return context
