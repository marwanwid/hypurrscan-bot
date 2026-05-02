"""
monitors/trade_monitor.py
Real-time WebSocket monitor for:
  - Large perp position opens > $10M
  - Large spot trades > $1M
"""

import asyncio
import json
import logging
from typing import Set

import websockets

from config import (
    HL_WS_URL,
    HL_API_URL,
    PERP_POSITION_THRESHOLD_USD,
    SPOT_TRADE_THRESHOLD_USD,
)
from utils.formatter import large_perp_trade_alert, large_spot_trade_alert
from utils.grouper import AlertGrouper

logger = logging.getLogger(__name__)

# Top perp coins to monitor (extend as needed)
TOP_PERP_COINS = [
    "BTC", "ETH", "SOL", "BNB", "AVAX", "MATIC", "ARB", "OP",
    "DOGE", "LINK", "UNI", "AAVE", "SUI", "APT", "TIA",
    "HYPE", "kPEPE", "WIF", "BONK", "JTO",
]

# Top spot coins on Hyperliquid
TOP_SPOT_COINS = ["HYPE", "PURR", "JEFF", "POINTS"]


class TradeMonitor:
    def __init__(self, grouper: AlertGrouper):
        self.grouper = grouper
        self._seen_tids: Set[int] = set()

    async def run(self):
        logger.info("TradeMonitor started via WebSocket")
        while True:
            try:
                await self._connect()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"WebSocket error: {e} — reconnecting in 10s")
                await asyncio.sleep(10)

    async def _connect(self):
        async with websockets.connect(
            HL_WS_URL,
            ping_interval=20,
            ping_timeout=10,
        ) as ws:
            logger.info("WebSocket connected")

            # Subscribe to trades for top perp coins
            for coin in TOP_PERP_COINS:
                sub = {"method": "subscribe", "subscription": {"type": "trades", "coin": coin}}
                await ws.send(json.dumps(sub))
                await asyncio.sleep(0.05)  # small delay to avoid overwhelming

            # Subscribe to spot trades
            for coin in TOP_SPOT_COINS:
                sub = {"method": "subscribe", "subscription": {"type": "trades", "coin": f"@{coin}"}}
                await ws.send(json.dumps(sub))
                await asyncio.sleep(0.05)

            logger.info(f"Subscribed to {len(TOP_PERP_COINS)} perp + {len(TOP_SPOT_COINS)} spot coins")

            async for raw in ws:
                try:
                    await self._handle(json.loads(raw))
                except Exception as e:
                    logger.debug(f"Message parse error: {e}")

    async def _handle(self, msg: dict):
        channel = msg.get("channel", "")
        data = msg.get("data", [])

        if channel != "trades":
            return
        if not isinstance(data, list):
            data = [data]

        for trade in data:
            tid = trade.get("tid")
            if tid and tid in self._seen_tids:
                continue
            if tid:
                self._seen_tids.add(tid)

            coin = trade.get("coin", "")
            side = trade.get("side", "")
            px = float(trade.get("px") or 0)
            sz = float(trade.get("sz") or 0)
            notional = px * sz

            is_spot = coin.startswith("@")
            display_coin = coin.lstrip("@")

            if is_spot:
                if notional >= SPOT_TRADE_THRESHOLD_USD:
                    msg = large_spot_trade_alert(display_coin, side, notional, px)
                    await self.grouper.add("Large Spot Trade", msg)
                    logger.info(f"Large SPOT trade: {display_coin} ${notional:,.0f}")
            else:
                if notional >= PERP_POSITION_THRESHOLD_USD:
                    users = trade.get("users", ["", ""])
                    address = users[0] if users else ""
                    msg = large_perp_trade_alert(display_coin, side, notional, px, address)
                    await self.grouper.add("Large Perp Position", msg)
                    logger.info(f"Large PERP trade: {display_coin} ${notional:,.0f}")

        # Prevent seen_tids from growing too large
        if len(self._seen_tids) > 10000:
            tids = list(self._seen_tids)
            self._seen_tids = set(tids[-5000:])
