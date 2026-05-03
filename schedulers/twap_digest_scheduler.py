"""
schedulers/twap_digest_scheduler.py
Sends a digest of active large TWAPs every TWAP_DIGEST_HOURS hours.
Menggunakan data real dari TWAPMonitor WebSocket (bukan HypurrScan API).
"""

import asyncio
import logging

from config import TWAP_DIGEST_HOURS, TWAP_DIGEST_THRESHOLD_USD
from utils.formatter import twap_digest
from utils.grouper import AlertGrouper

logger = logging.getLogger(__name__)


class TWAPDigestScheduler:
    def __init__(self, grouper: AlertGrouper, twap_monitor=None):
        self.grouper = grouper
        self.twap_monitor = twap_monitor
        self._interval = TWAP_DIGEST_HOURS * 3600

    async def run(self):
        logger.info(f"TWAPDigestScheduler started (every {TWAP_DIGEST_HOURS}h)")
        await asyncio.sleep(15)
        while True:
            await self._send_digest()
            await asyncio.sleep(self._interval)

    async def _send_digest(self):
        twaps = []
        if self.twap_monitor:
            twaps = self.twap_monitor.get_active_twaps(min_notional=TWAP_DIGEST_THRESHOLD_USD)

        msg = twap_digest(twaps)
        await self.grouper.add("Scheduled Digest", msg)
        logger.info(f"TWAP digest sent: {len(twaps)} active large TWAPs")