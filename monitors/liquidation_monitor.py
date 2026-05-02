"""
monitors/liquidation_monitor.py
Menggunakan official Hyperliquid API 'liquidatable' endpoint.
"""

import asyncio
from typing import Set, Dict

from config import LIQUIDATION_THRESHOLD_USD, POLL_LIQUIDATION_SEC
from monitors.base import BaseMonitor
from utils.formatter import liquidation_alert
from utils.grouper import AlertGrouper


class LiquidationMonitor(BaseMonitor):
    def __init__(self, grouper: AlertGrouper):
        super().__init__(grouper, poll_interval=POLL_LIQUIDATION_SEC)
        self._prev_snapshot: Dict[str, float] = {}

    async def tick(self):
        resp = await self.hl_post({"type": "liquidatable"})
        if not resp or not isinstance(resp, list):
            return

        current_snapshot: Dict[str, float] = {}

        for item in resp:
            address = item.get("user", "")
            if not address:
                continue

            state = item.get("clearinghouseState", {})
            margin = state.get("marginSummary", {})
            account_value = float(margin.get("accountValue") or 0)
            current_snapshot[address] = account_value

            # Alert: address baru masuk liquidatable list dengan AV > threshold
            if address not in self._prev_snapshot and account_value >= LIQUIDATION_THRESHOLD_USD:
                positions = []
                for pos in state.get("assetPositions", []):
                    p = pos.get("position", {})
                    positions.append({
                        "coin": p.get("coin", "?"),
                        "szi": p.get("szi", "0"),
                        "px": p.get("entryPx", "0"),
                    })
                leverage_type = "Cross"
                msg = liquidation_alert(address, account_value, positions, leverage_type)
                await self.grouper.add("Liquidations", msg)
                self.logger.info(f"Liquidation alert: {address[:10]}... | ${account_value:,.0f}")

        self._prev_snapshot = current_snapshot