"""
monitors/twap_monitor.py
Deteksi TWAP besar via WebSocket fills — semua pair (perp, spot, HIP-3).
"""

import asyncio
import json
import logging
from typing import Set

import aiohttp
import websockets

from config import HL_API_URL, HL_WS_URL, TWAP_ALERT_THRESHOLD_USD
from utils.formatter import twap_alert
from utils.grouper import AlertGrouper

logger = logging.getLogger(__name__)


class TWAPMonitor:
    def __init__(self, grouper: AlertGrouper):
        self.grouper = grouper
        self._twap_notional: dict = {}
        self._alerted_twaps: Set[str] = set()
        self._all_coins: list = []

    async def run(self):
        logger.info("TWAPMonitor started via WebSocket fills — all pairs")
        await self._fetch_all_coins()
        while True:
            try:
                await self._connect()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"TWAP WS reconnecting... ({e})")
                await asyncio.sleep(15)

    async def _fetch_all_coins(self):
        """Fetch semua coin dari HL API — perp + spot."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                # Perp coins
                async with session.post(HL_API_URL, json={"type": "metaAndAssetCtxs"}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list) and len(data) >= 1:
                            universe = data[0].get("universe", [])
                            perp_coins = [u["name"] for u in universe if "name" in u]
                            self._all_coins.extend(perp_coins)
                            logger.info(f"TWAP: fetched {len(perp_coins)} perp coins")

                # Spot coins
                async with session.post(HL_API_URL, json={"type": "spotMeta"}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        tokens = data.get("tokens", [])
                        spot_coins = [f"@{t['name']}" for t in tokens if "name" in t]
                        self._all_coins.extend(spot_coins)
                        logger.info(f"TWAP: fetched {len(spot_coins)} spot coins")

        except Exception as e:
            logger.error(f"TWAP coin fetch error: {e}")
            # Fallback ke list manual kalau API gagal
            self._all_coins = [
                "BTC", "ETH", "SOL", "BNB", "AVAX", "ARB", "OP",
                "DOGE", "LINK", "SUI", "APT", "HYPE", "WIF", "JTO",
                "@HYPE", "@PURR",
            ]

        logger.info(f"TWAP monitoring {len(self._all_coins)} total pairs")

    async def _connect(self):
        async with websockets.connect(HL_WS_URL, ping_interval=20) as ws:
            # Subscribe ke semua coins dalam batch
            for coin in self._all_coins:
                sub = {"method": "subscribe", "subscription": {"type": "trades", "coin": coin}}
                await ws.send(json.dumps(sub))
                await asyncio.sleep(0.03)

            logger.info(f"TWAP subscribed to {len(self._all_coins)} pairs")

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

            if self._twap_notional[key] >= TWAP_ALERT_THRESHOLD_USD and key not in self._alerted_twaps:
                self._alerted_twaps.add(key)
                users = trade.get("users", ["", ""])
                address = users[0] if users else ""
                display_coin = coin.lstrip("@")
                msg = twap_alert(display_coin, side, self._twap_notional[key], address, 0)
                await self.grouper.add("TWAP Watch", msg)
                logger.info(f"TWAP alert: {display_coin} ${self._twap_notional[key]:,.0f}")

        if len(self._alerted_twaps) > 2000:
            self._alerted_twaps = set(list(self._alerted_twaps)[-1000:])