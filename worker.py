#!/usr/bin/env python3
"""Vast Serverless PyWorker for TRON suffix-only vanity find."""

from __future__ import annotations

import os

from vastai import BenchmarkConfig, HandlerConfig, LogActionConfig, Worker, WorkerConfig


MODEL_SERVER_URL = os.environ.get("VAST_MODEL_SERVER_URL", "http://127.0.0.1")
MODEL_SERVER_PORT = int(os.environ.get("VAST_MODEL_SERVER_PORT", "18000"))
MODEL_LOG_FILE = os.environ.get("VAST_MODEL_LOG_FILE", "/var/log/tron-vanity/model.log")


def constant_find_workload(payload: dict) -> float:
    duration = payload.get("duration_seconds", 8)
    try:
        return max(1.0, float(duration))
    except (TypeError, ValueError):
        return 8.0


def health_benchmark_payload() -> dict:
    return {"mode": "health"}


worker_config = WorkerConfig(
    model_server_url=MODEL_SERVER_URL,
    model_server_port=MODEL_SERVER_PORT,
    model_log_file=MODEL_LOG_FILE,
    handlers=[
        HandlerConfig(
            route="/health",
            allow_parallel_requests=True,
            max_queue_time=10.0,
            workload_calculator=lambda payload: 1.0,
            benchmark_config=BenchmarkConfig(
                generator=health_benchmark_payload,
                runs=1,
                concurrency=1,
            ),
        ),
        HandlerConfig(
            route="/find",
            allow_parallel_requests=False,
            max_queue_time=30.0,
            workload_calculator=constant_find_workload,
        ),
    ],
    log_action_config=LogActionConfig(
        on_load=["Application startup complete."],
        on_error=["Traceback (most recent call last):", "RuntimeError:", "Exception:"],
        on_info=["Vast model backend listening"],
    ),
)


if __name__ == "__main__":
    Worker(worker_config).run()
