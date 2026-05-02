"""
monitors/twap_monitor.py
Deteksi TWAP besar via WebSocket fills.
Fill dengan twapId non-null = TWAP fill.
"""

import asyncio
import json
import logging
from typing import Set

import websockets

from config import HL_WS_URL, TWAP_ALERT_THRESHOLD_USD
from utils.formatter import twap_alert
from utils.grouper import AlertGrouper

logger = logging.getLogger(__name__)

TOP_PERP_COINS = [
    "BTC", "ETH", "SOL", "BNB", "AVAX", "ARB", "OP",
    "DOGE", "LINK", "SUI", "APT", "HYPE", "WIF", "JTO",
]


class TWAPMonitor:
    def __init__(self, grouper: AlertGrouper):
        self.grouper = grouper
        # Track (coin, twapId) -> total notional accumulated
        self._twap_notional: dict = {}
        self._alerted_twaps: Set[str] = set()

    async def run(self):
        logger.info("TWAPMonitor started via WebSocket fills")
        while True:
            try:
                await self._connect()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"TWAP WS error: {e} — reconnecting in 15s")
                await asyncio.sleep(15)

    async def _connect(self):
        async with websockets.connect(HL_WS_URL, ping_interval=20) as ws:
            for coin in TOP_PERP_COINS:
                sub = {"method": "subscribe", "subscription": {"type": "trades", "coin": coin}}
                await ws.send(json.dumps(sub))
                await asyncio.sleep(0.05)

            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    if msg.get("channel") == "trades":
                        await self._handle(msg.get("data", []))
                except Exception:
                    pass

    async def _handle(self, trades: list):
        if not isinstance(trades, list):
            trades = [trades]
        for trade in trades:
            # TWAP fills have hash 0x000...000
            tx_hash = trade.get("hash", "")
            is_twap = tx_hash == "0x" + "0" * 64

            if not is_twap:
                continue

            coin = trade.get("coin", "")
            side = trade.get("side", "B")
            px = float(trade.get("px") or 0)
            sz = float(trade.get("sz") or 0)
            notional = px * sz
            twap_id = str(trade.get("oid") or trade.get("tid") or "")

            key = f"{coin}_{twap_id}"
            self._twap_notional[key] = self._twap_notional.get(key, 0) + notional

            # Alert sekali kalau total notional sudah lewat threshold
            if self._twap_notional[key] >= TWAP_ALERT_THRESHOLD_USD and key not in self._alerted_twaps:
                self._alerted_twaps.add(key)
                users = trade.get("users", ["", ""])
                address = users[0] if users else ""
                msg = twap_alert(coin, side, self._twap_notional[key], address, 0)
                await self.grouper.add("TWAP Watch", msg)
                logger.info(f"TWAP alert: {coin} ${self._twap_notional[key]:,.0f}")

        # Cleanup
        if len(self._alerted_twaps) > 2000:
            self._alerted_twaps = set(list(self._alerted_twaps)[-1000:])