"""
schedulers/fees_scheduler.py
Sends a 24H protocol fees digest every FEES_DIGEST_HOURS hours.
"""

import asyncio
import logging

from config import FEES_DIGEST_HOURS, HYPURRSCAN_API_URL, HL_API_URL
from utils.formatter import fees_digest
from utils.grouper import AlertGrouper

logger = logging.getLogger(__name__)


class FeesScheduler:
    def __init__(self, grouper: AlertGrouper):
        self.grouper = grouper
        self._interval = FEES_DIGEST_HOURS * 3600

    async def run(self):
        logger.info(f"FeesScheduler started (every {FEES_DIGEST_HOURS}h)")
        # First digest after 10 seconds (startup message)
        await asyncio.sleep(10)
        while True:
            await self._send_digest()
            await asyncio.sleep(self._interval)

    async def _send_digest(self):
        total_fees = await self._fetch_fees()
        msg = fees_digest(total_fees)
        await self.grouper.add("Scheduled Digest", msg)
        logger.info(f"Fees digest sent: ${total_fees:,.0f}")

    async def _fetch_fees(self) -> float:
        """Try HypurrScan first, then estimate from HL API."""
        import aiohttp

        # Try HypurrScan stats
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                for path in ["/stats", "/fees", "/dashboard", "/summary"]:
                    async with session.get(f"{HYPURRSCAN_API_URL}{path}") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            # Try common field names
                            for key in ["fees24h", "fees_24h", "dailyFees", "totalFees24h",
                                        "volume24h", "vol24h", "fee24h"]:
                                val = data.get(key) if isinstance(data, dict) else None
                                if val is not None:
                                    return float(val)
        except Exception as e:
            logger.debug(f"HypurrScan fees fetch error: {e}")

        # Fallback: estimate from HL metaAndAssetCtxs (premium * OI ≈ fee proxy)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(HL_API_URL, json={"type": "metaAndAssetCtxs"}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list) and len(data) >= 2:
                            asset_ctxs = data[1]
                            # Rough fee estimate: 0.025% maker/taker on daily volume
                            total_vol = sum(
                                float(ctx.get("dayNtlVlm") or 0)
                                for ctx in asset_ctxs
                                if isinstance(ctx, dict)
                            )
                            # ~0.02% avg fee rate
                            return total_vol * 0.0002
        except Exception as e:
            logger.debug(f"HL fees fallback error: {e}")

        return 0.0
