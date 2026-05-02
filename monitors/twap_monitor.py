"""
monitors/twap_monitor.py
Polls HypurrScan for new active TWAPs with notional > $1M.
"""

from typing import Set

from config import TWAP_ALERT_THRESHOLD_USD, POLL_TWAP_SEC
from monitors.base import BaseMonitor
from utils.formatter import twap_alert
from utils.grouper import AlertGrouper


class TWAPMonitor(BaseMonitor):
    def __init__(self, grouper: AlertGrouper):
        super().__init__(grouper, poll_interval=POLL_TWAP_SEC)
        self._seen_ids: Set[str] = set()

    async def tick(self):
        data = await self.hypurrscan_get("/twaps", params={"status": "active", "limit": 100})
        if data is None:
            data = await self.hypurrscan_get("/twap", params={"status": "active", "limit": 100})
        if data is None:
            return

        twaps = data if isinstance(data, list) else data.get("data", data.get("twaps", []))

        for twap in twaps:
            twap_id = str(
                twap.get("id")
                or twap.get("twapId")
                or twap.get("twap_id")
                or twap.get("hash", "")
            )
            if not twap_id or twap_id in self._seen_ids:
                continue

            # Notional = size * price (or directly provided)
            notional = float(
                twap.get("notional")
                or twap.get("totalNotional")
                or twap.get("total_notional")
                or 0
            )
            if notional == 0:
                sz = float(twap.get("sz") or twap.get("size") or 0)
                px = float(twap.get("px") or twap.get("price") or 0)
                notional = sz * px

            if notional < TWAP_ALERT_THRESHOLD_USD:
                continue

            self._seen_ids.add(twap_id)

            coin = twap.get("coin") or twap.get("asset") or "?"
            side = twap.get("side") or twap.get("isBuy", "B")
            address = twap.get("user") or twap.get("address") or ""
            duration = int(twap.get("duration") or twap.get("durationMinutes") or 0)

            msg = twap_alert(coin, side, notional, address, duration)
            await self.grouper.add("TWAP Watch", msg)
            self.logger.info(f"TWAP alert: {coin} | ${notional:,.0f}")

        if len(self._seen_ids) > 5000:
            self._seen_ids = set(list(self._seen_ids)[-2500:])
