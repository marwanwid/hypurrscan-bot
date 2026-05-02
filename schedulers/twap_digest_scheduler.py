"""
schedulers/twap_digest_scheduler.py
Sends a digest of active large TWAPs every TWAP_DIGEST_HOURS hours.
"""

import asyncio
import logging

import aiohttp

from config import TWAP_DIGEST_HOURS, TWAP_DIGEST_THRESHOLD_USD, HYPURRSCAN_API_URL
from utils.formatter import twap_digest
from utils.grouper import AlertGrouper

logger = logging.getLogger(__name__)


class TWAPDigestScheduler:
    def __init__(self, grouper: AlertGrouper):
        self.grouper = grouper
        self._interval = TWAP_DIGEST_HOURS * 3600

    async def run(self):
        logger.info(f"TWAPDigestScheduler started (every {TWAP_DIGEST_HOURS}h)")
        await asyncio.sleep(15)  # stagger vs fees digest
        while True:
            await self._send_digest()
            await asyncio.sleep(self._interval)

    async def _send_digest(self):
        twaps = await self._fetch_active_twaps()
        msg = twap_digest(twaps)
        await self.grouper.add("Scheduled Digest", msg)
        logger.info(f"TWAP digest sent: {len(twaps)} active large TWAPs")

    async def _fetch_active_twaps(self) -> list:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                for path in ["/twaps", "/twap", "/active-twaps"]:
                    params = {"status": "active", "limit": 100}
                    async with session.get(f"{HYPURRSCAN_API_URL}{path}", params=params) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        twaps_raw = data if isinstance(data, list) else data.get("data", data.get("twaps", []))

                        result = []
                        for t in twaps_raw:
                            sz = float(t.get("sz") or t.get("size") or 0)
                            px = float(t.get("px") or t.get("price") or 0)
                            notional = float(
                                t.get("notional") or t.get("totalNotional") or sz * px or 0
                            )
                            if notional < TWAP_DIGEST_THRESHOLD_USD:
                                continue
                            filled = float(t.get("filledSz") or t.get("filled_sz") or 0)
                            filled_pct = (filled / sz * 100) if sz > 0 else 0
                            result.append({
                                "coin": t.get("coin") or t.get("asset") or "?",
                                "side": t.get("side") or "?",
                                "notional": notional,
                                "filled_pct": filled_pct,
                            })

                        result.sort(key=lambda x: x["notional"], reverse=True)
                        return result

        except Exception as e:
            logger.error(f"TWAP digest fetch error: {e}")
        return []
