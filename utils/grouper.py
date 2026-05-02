"""
utils/grouper.py — Collects alerts and flushes them as grouped messages
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Callable

from config import ALERT_GROUP_WINDOW_SECONDS, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    category: str
    message: str
    timestamp: datetime = field(default_factory=datetime.now)


class AlertGrouper:
    def __init__(self):
        self._buffer: List[Alert] = []
        self._lock = asyncio.Lock()

    async def add(self, category: str, message: str):
        """Add an alert to the buffer."""
        async with self._lock:
            self._buffer.append(Alert(category=category, message=message))
        logger.debug(f"Alert buffered [{category}]")

    async def flush_loop(self, bot):
        """Background task: flush buffer every ALERT_GROUP_WINDOW_SECONDS."""
        logger.info(f"GroupFlusher: flushing every {ALERT_GROUP_WINDOW_SECONDS}s")
        while True:
            await asyncio.sleep(ALERT_GROUP_WINDOW_SECONDS)
            await self._flush(bot)

    async def _flush(self, bot):
        async with self._lock:
            if not self._buffer:
                return
            alerts = self._buffer.copy()
            self._buffer.clear()

        # Group by category
        grouped: dict[str, List[str]] = defaultdict(list)
        for alert in alerts:
            grouped[alert.category].append(alert.message)

        # Build message(s) — Telegram has 4096 char limit per message
        chunks = []
        for category, messages in grouped.items():
            if len(messages) == 1:
                chunks.append(messages[0])
            else:
                header = f"📦 *{category}* — {len(messages)} events\n"
                body = "\n\n".join(messages)
                chunks.append(header + body)

        full_text = "\n\n━━━━━━━━━━━━━━━━━━━━\n\n".join(chunks)

        # Split if too long
        for part in self._split(full_text):
            try:
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=part,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logger.error(f"Failed to send alert: {e}")

    @staticmethod
    def _split(text: str, limit: int = 4000) -> List[str]:
        if len(text) <= limit:
            return [text]
        parts = []
        while text:
            parts.append(text[:limit])
            text = text[limit:]
        return parts
