"""
monitors/base.py — Abstract base class for all monitors
"""

import asyncio
import logging
from abc import ABC, abstractmethod

import aiohttp

from utils.grouper import AlertGrouper


class BaseMonitor(ABC):
    def __init__(self, grouper: AlertGrouper, poll_interval: int = 60):
        self.grouper = grouper
        self.poll_interval = poll_interval
        self.logger = logging.getLogger(self.__class__.__name__)
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            )
        return self._session

    async def hl_post(self, payload: dict) -> dict | None:
        """POST to Hyperliquid info endpoint."""
        from config import HL_API_URL
        try:
            session = await self._get_session()
            async with session.post(HL_API_URL, json=payload) as resp:
                if resp.status == 200:
                    return await resp.json()
                self.logger.warning(f"HL API returned {resp.status}")
        except Exception as e:
            self.logger.error(f"HL API error: {e}")
        return None

    async def hypurrscan_get(self, path: str, params: dict = None) -> dict | list | None:
        """GET from HypurrScan API."""
        from config import HYPURRSCAN_API_URL
        try:
            session = await self._get_session()
            url = f"{HYPURRSCAN_API_URL}{path}"
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
                self.logger.warning(f"HypurrScan {path} returned {resp.status}")
        except Exception as e:
            self.logger.error(f"HypurrScan API error [{path}]: {e}")
        return None

    async def run(self):
        """Main monitor loop — override tick() in subclasses."""
        self.logger.info(f"Monitor started (interval={self.poll_interval}s)")
        await asyncio.sleep(5)  # stagger startup
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger.error(f"Unhandled error in tick(): {e}", exc_info=True)
            await asyncio.sleep(self.poll_interval)

    @abstractmethod
    async def tick(self):
        """Called every poll_interval seconds."""
        ...
