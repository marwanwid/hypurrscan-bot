"""
monitors/oi_monitor.py
Tracks Open Interest per coin and alerts on >20% spike within one poll window.
"""

from typing import Dict

from config import OI_SPIKE_PERCENT, POLL_OI_SEC
from monitors.base import BaseMonitor
from utils.formatter import oi_spike_alert
from utils.grouper import AlertGrouper


class OIMonitor(BaseMonitor):
    def __init__(self, grouper: AlertGrouper):
        super().__init__(grouper, poll_interval=POLL_OI_SEC)
        self._prev_oi: Dict[str, float] = {}

    async def tick(self):
        resp = await self.hl_post({"type": "metaAndAssetCtxs"})
        if not resp or not isinstance(resp, list) or len(resp) < 2:
            return

        universe = resp[0].get("universe", [])
        asset_ctxs = resp[1]

        for i, ctx in enumerate(asset_ctxs):
            if i >= len(universe):
                break
            coin = universe[i].get("name", f"asset_{i}")
            try:
                oi = float(ctx.get("openInterest", 0))
            except (TypeError, ValueError):
                continue

            prev = self._prev_oi.get(coin)
            if prev is not None and prev > 0 and oi > 0:
                pct_change = ((oi - prev) / prev) * 100
                if abs(pct_change) >= OI_SPIKE_PERCENT:
                    msg = oi_spike_alert(coin, prev, oi, pct_change)
                    await self.grouper.add("OI Spike", msg)
                    self.logger.info(f"OI spike: {coin} {pct_change:+.1f}%")

            self._prev_oi[coin] = oi
