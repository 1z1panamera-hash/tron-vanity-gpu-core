from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

from .config import Settings
from .database import ControllerDatabase


CallbackSender = Callable[[str, dict[str, object]], Awaitable[bool]]


class CallbackDispatcher:
    def __init__(
        self,
        settings: Settings,
        database: ControllerDatabase,
        sender: CallbackSender,
    ):
        self.settings = settings
        self.database = database
        self.sender = sender
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        if not self.settings.callback_url:
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="vanity18035-callbacks")

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _run(self) -> None:
        try:
            while not self._stopping:
                rows = self.database.due_callbacks()
                if not rows:
                    await asyncio.sleep(0.25)
                    continue
                for row in rows:
                    delivered = False
                    error: str | None = None
                    try:
                        payload = json.loads(str(row["payload_json"]))
                        delivered = await self.sender(self.settings.callback_url, payload)
                        if not delivered:
                            error = "callback returned a non-2xx response"
                    except asyncio.CancelledError:
                        raise
                    except Exception as caught:  # The payload itself is never logged.
                        error = type(caught).__name__
                    self.database.finish_callback(str(row["event_id"]), delivered, error)
        except asyncio.CancelledError:
            return
