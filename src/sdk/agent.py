"""Base agent class for the Orchestrator SDK."""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    def __init__(self, agent_id: str, name: str, config: Optional[Dict] = None):
        self.agent_id = agent_id
        self.name = name
        self.config = config or {}
        self._running = False
        self._metadata: Dict[str, Any] = {}

    @abstractmethod
    async def setup(self) -> None:
        pass

    @abstractmethod
    async def handle_task(self, task: Dict[str, Any]) -> Any:
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        pass

    async def run(self) -> None:
        self._running = True
        try:
            await self.setup()
            logger.info(f"Agent {self.name} ({self.agent_id}) started")
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.cleanup()
            logger.info(f"Agent {self.name} stopped")

    def stop(self) -> None:
        self._running = False

    def set_metadata(self, key: str, value: Any) -> None:
        self._metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        return self._metadata.get(key, default)

# 2019-04-19T17:53:22 update

# 2019-05-21T12:12:13 update

# 2019-06-05T14:31:06 update

# 2019-08-19T14:06:12 update

# 2019-09-03T17:18:33 update

# 2019-09-25T19:10:47 update

# 2019-10-04T18:47:05 update

# 2019-11-12T14:58:03 update

# 2019-12-20T08:28:57 update

# 2020-01-03T17:08:23 update

# 2020-03-02T17:34:38 update

# 2020-04-15T12:45:59 update

# 2020-05-14T14:15:44 update

# 2020-06-02T14:58:36 update

# 2020-06-09T10:22:41 update

# 2020-08-19T17:50:10 update

# 2020-08-20T16:16:54 update

# 2020-09-30T14:39:21 update

# 2020-10-05T16:23:46 update

# 2020-10-20T16:37:47 update

# 2020-12-24T10:51:38 update

# 2021-01-03T14:46:44 update

# 2021-03-29T15:14:26 update

# 2021-04-28T08:38:35 update

# 2021-05-05T18:15:02 update

# 2021-05-14T11:50:24 update

# 2021-08-27T15:46:20 update

# 2021-10-01T09:45:52 update

# 2021-10-05T15:02:18 update

# 2021-10-06T15:28:16 update

# 2021-12-01T15:27:33 update

# 2022-02-03T20:39:59 update

# 2022-03-15T17:35:15 update

# 2022-04-20T09:20:39 update

# 2022-04-23T15:58:57 update

# 2022-04-26T16:50:35 update

# 2022-05-04T16:39:27 update

# 2022-06-09T09:40:36 update

# 2022-07-19T13:53:48 update

# 2022-07-26T09:47:41 update

# 2022-09-06T19:08:33 update

# 2022-10-18T08:09:23 update

# 2023-01-24T18:53:49 update

# 2023-02-06T09:11:57 update

# 2023-02-21T16:06:32 update

# 2023-03-29T08:00:38 update

# 2023-07-19T19:52:34 update

# 2023-08-21T13:49:16 update

# 2023-10-17T16:58:29 update

# 2023-11-03T12:56:36 update

# 2023-11-15T15:41:17 update

# 2023-12-04T09:08:16 update

# 2023-12-13T14:12:12 update

# 2024-01-02T13:53:28 update

# 2024-01-26T11:12:15 update

# 2024-02-21T16:48:18 update

# 2024-03-14T17:47:08 update

# 2024-06-10T17:56:32 update

# 2024-07-08T11:56:01 update

# 2024-07-09T14:25:37 update

# 2024-07-31T20:02:11 update

# 2024-08-01T09:48:37 update

# 2024-12-27T12:17:32 update

# 2025-01-01T08:19:55 update

# 2025-01-21T17:09:08 update

# 2025-04-24T17:34:50 update

# 2025-05-09T10:06:39 update

# 2025-05-22T14:47:50 update

# 2025-06-02T08:26:58 update

# 2025-07-07T18:55:00 update

# 2025-07-16T19:08:21 update

# 2025-07-17T14:36:45 update

# 2025-08-28T11:31:25 update

# 2025-09-03T12:47:50 update

# 2025-09-30T19:29:34 update

# 2025-12-16T17:31:48 update

# 2026-01-20T12:21:20 update

# 2026-02-19T19:52:05 update

# 2026-04-20T17:39:04 update
