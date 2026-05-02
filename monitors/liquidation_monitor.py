"""
monitors/liquidation_monitor.py
Polls HypurrScan for large liquidations (>$1M account value).
Falls back to Hyperliquid liquidatable endpoint.
"""

import logging
from typing import Set

from config import LIQUIDATION_THRESHOLD_USD, POLL_LIQUIDATION_SEC
from monitors.base import BaseMonitor
from utils.formatter import liquidation_alert
from utils.grouper import AlertGrouper

logger = logging.getLogger(__name__)


class LiquidationMonitor(BaseMonitor):
    def __init__(self, grouper: AlertGrouper):
        super().__init__(grouper, poll_interval=POLL_LIQUIDATION_SEC)
        self._seen_ids: Set[str] = set()

    async def tick(self):
        # Primary: HypurrScan /liquidations endpoint
        data = await self.hypurrscan_get("/liquidations", params={"limit": 50})

        if data is None:
            # Fallback: Hyperliquid official "liquidatable" endpoint
            await self._hl_fallback()
            return

        liquidations = data if isinstance(data, list) else data.get("data", data.get("liquidations", []))

        for liq in liquidations:
            # HypurrScan response shape (adjust keys to match actual API)
            liq_id = str(liq.get("id") or liq.get("hash") or liq.get("txHash", ""))
            if not liq_id or liq_id in self._seen_ids:
                continue
            self._seen_ids.add(liq_id)

            account_value = float(liq.get("accountValue") or liq.get("account_value") or 0)
            if account_value < LIQUIDATION_THRESHOLD_USD:
                continue

            address = liq.get("user") or liq.get("address") or ""
            leverage_type = liq.get("leverageType") or liq.get("leverage_type") or "Cross"
            positions = liq.get("liquidatedPositions") or liq.get("positions") or []

            msg = liquidation_alert(address, account_value, positions, leverage_type)
            await self.grouper.add("Liquidations", msg)
            self.logger.info(f"Liquidation alert: {address} | ${account_value:,.0f}")

        # Keep seen_ids from growing unbounded
        if len(self._seen_ids) > 5000:
            self._seen_ids = set(list(self._seen_ids)[-2500:])

    async def _hl_fallback(self):
        """Use Hyperliquid's 'liquidatable' info endpoint as fallback."""
        resp = await self.hl_post({"type": "liquidatable"})
        if not resp:
            return

        for item in resp if isinstance(resp, list) else []:
            address = item.get("user", "")
            uid = f"liq_fallback_{address}"
            if uid in self._seen_ids:
                continue

            state = item.get("clearinghouseState", {})
            margin = state.get("marginSummary", {})
            account_value = float(margin.get("accountValue", 0))

            if account_value < LIQUIDATION_THRESHOLD_USD:
                continue

            self._seen_ids.add(uid)
            msg = liquidation_alert(address, account_value, [], "Cross")
            await self.grouper.add("Liquidations", msg)
            self.logger.info(f"Fallback liquidation alert: {address} | ${account_value:,.0f}")
