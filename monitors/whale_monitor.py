"""
monitors/whale_monitor.py
Monitors watchlist addresses for large deposits, withdrawals, and liquidations.
"""

import asyncio
from typing import Dict

from config import (
    WHALE_DEPOSIT_THRESHOLD_USD,
    WHALE_WITHDRAW_THRESHOLD_USD,
    WHALE_LIQUIDATION_THRESHOLD_USD,
    POLL_WHALE_SEC,
)
from monitors.base import BaseMonitor
from utils.formatter import whale_alert
from utils.grouper import AlertGrouper
from utils.storage import Storage


class WhaleMonitor(BaseMonitor):
    def __init__(self, grouper: AlertGrouper, storage: Storage):
        super().__init__(grouper, poll_interval=POLL_WHALE_SEC)
        self.storage = storage
        # Track last known account value per address to detect changes
        self._prev_state: Dict[str, dict] = {}

    async def tick(self):
        wallets = self.storage.get_wallets()
        if not wallets:
            return

        for address, meta in wallets.items():
            await self._check_address(address, meta.get("label", address[:10]))
            await asyncio.sleep(0.5)  # small delay between addresses

    async def _check_address(self, address: str, label: str):
        resp = await self.hl_post({"type": "clearinghouseState", "user": address})
        if not resp:
            return

        margin = resp.get("marginSummary", {})
        account_value = float(margin.get("accountValue") or 0)
        withdrawable = float(resp.get("withdrawable") or 0)

        prev = self._prev_state.get(address)

        if prev is None:
            # First snapshot — just store, don't alert
            self._prev_state[address] = {
                "accountValue": account_value,
                "withdrawable": withdrawable,
            }
            return

        prev_av = prev.get("accountValue", account_value)
        prev_wd = prev.get("withdrawable", withdrawable)

        delta_av = account_value - prev_av

        # Detect large deposit (account value grew significantly)
        if delta_av >= WHALE_DEPOSIT_THRESHOLD_USD:
            msg = whale_alert(
                address, label, "deposit", delta_av,
                f"AV: ${prev_av:,.0f} → ${account_value:,.0f}"
            )
            await self.grouper.add("Whale Intel", msg)
            self.logger.info(f"Whale DEPOSIT: {label} +${delta_av:,.0f}")

        # Detect large withdrawal (account value dropped significantly)
        elif delta_av <= -WHALE_WITHDRAW_THRESHOLD_USD:
            msg = whale_alert(
                address, label, "withdraw", abs(delta_av),
                f"AV: ${prev_av:,.0f} → ${account_value:,.0f}"
            )
            await self.grouper.add("Whale Intel", msg)
            self.logger.info(f"Whale WITHDRAW: {label} -${abs(delta_av):,.0f}")

        # Detect potential liquidation (account value dropped dramatically, near zero)
        if account_value < WHALE_LIQUIDATION_THRESHOLD_USD and prev_av >= WHALE_LIQUIDATION_THRESHOLD_USD * 2:
            msg = whale_alert(
                address, label, "liquidation", prev_av - account_value,
                f"Account value collapsed: ${prev_av:,.0f} → ${account_value:,.0f}"
            )
            await self.grouper.add("Whale Intel", msg)
            self.logger.info(f"Whale LIQUIDATION: {label}")

        self._prev_state[address] = {
            "accountValue": account_value,
            "withdrawable": withdrawable,
        }
