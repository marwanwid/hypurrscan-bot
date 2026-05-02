"""
monitors/trade_monitor.py
Real-time WebSocket monitor — semua pair perp + spot.
  - Large perp trade > $1M
  - Large spot trade > $1M
"""

import asyncio
import json
import logging
from typing import Set

import aiohttp
import websockets

from config import HL_API_URL, HL_WS_URL, PERP_POSITION_THRESHOLD_USD, SPOT_TRADE_THRESHOLD_USD
from utils.formatter import large_perp_trade_alert, large_spot_trade_alert
from utils.grouper import AlertGrouper

logger = logging.getLogger(__name__)


class TradeMonitor:
    def __init__(self, grouper: AlertGrouper):
        self.grouper = grouper
        self._seen_tids: Set[int] = set()
        self._perp_coins: list = []
        self._spot_coins: list = []

    async def run(self):
        logger.info("TradeMonitor started — fetching all pairs")
        await self._fetch_all_coins()
        while True:
            try:
                await self._connect()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"TradeMonitor reconnecting... ({e})")
                await asyncio.sleep(10)

    async def _fetch_all_coins(self):
        """Fetch semua perp dan spot coins dari HL API."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                # Perp
                async with session.post(HL_API_URL, json={"type": "metaAndAssetCtxs"}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list) and len(data) >= 1:
                            universe = data[0].get("universe", [])
                            self._perp_coins = [u["name"] for u in universe if "name" in u]
                            logger.info(f"TradeMonitor: {len(self._perp_coins)} perp coins")

                # Spot
                async with session.post(HL_API_URL, json={"type": "spotMeta"}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        tokens = data.get("tokens", [])
                        self._spot_coins = [t["name"] for t in tokens if "name" in t]
                        logger.info(f"TradeMonitor: {len(self._spot_coins)} spot coins")

        except Exception as e:
            logger.error(f"TradeMonitor coin fetch error: {e}")
            # Fallback
            self._perp_coins = [
                "BTC", "ETH", "SOL", "BNB", "AVAX", "ARB", "OP",
                "DOGE", "LINK", "SUI", "APT", "HYPE", "WIF", "JTO",
            ]
            self._spot_coins = ["HYPE", "PURR", "JEFF", "POINTS"]

        logger.info(f"TradeMonitor: total {len(self._perp_coins)} perp + {len(self._spot_coins)} spot")

    async def _connect(self):
        async with websockets.connect(HL_WS_URL, ping_interval=20, ping_timeout=10) as ws:
            # Subscribe perp
            for coin in self._perp_coins:
                sub = {"method": "subscribe", "subscription": {"type": "trades", "coin": coin}}
                await ws.send(json.dumps(sub))
                await asyncio.sleep(0.03)

            # Subscribe spot (prefix @)
            for coin in self._spot_coins:
                sub = {"method": "subscribe", "subscription": {"type": "trades", "coin": f"@{coin}"}}
                await ws.send(json.dumps(sub))
                await asyncio.sleep(0.03)

            logger.info(f"TradeMonitor subscribed: {len(self._perp_coins)} perp + {len(self._spot_coins)} spot")

            async for raw in ws:
                try:
                    await self._handle(json.loads(raw))
                except Exception as e:
                    logger.debug(f"Parse error: {e}")

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
                    logger.info(f"Large SPOT: {display_coin} ${notional:,.0f}")
            else:
                if notional >= PERP_POSITION_THRESHOLD_USD:
                    users = trade.get("users", ["", ""])
                    address = users[0] if users else ""
                    msg = large_perp_trade_alert(display_coin, side, notional, px, address)
                    await self.grouper.add("Large Perp Position", msg)
                    logger.info(f"Large PERP: {display_coin} ${notional:,.0f}")

        if len(self._seen_tids) > 10000:
            self._seen_tids = set(list(self._seen_tids)[-5000:])