"""
monitors/liquidation_monitor.py
Deteksi liquidasi COMPLETED via WebSocket trades.
Liquidation trades di Hyperliquid punya field 'liquidation' di dalam trade object.
"""

import asyncio
import json
import logging
from typing import Set

import aiohttp
import websockets

from config import HL_API_URL, HL_WS_URL, LIQUIDATION_THRESHOLD_USD
from utils.formatter import liquidation_alert
from utils.grouper import AlertGrouper

logger = logging.getLogger(__name__)


class LiquidationMonitor:
    def __init__(self, grouper: AlertGrouper):
        self.grouper = grouper
        self._seen_tids: Set[str] = set()
        self._perp_coins: list = []

    async def run(self):
        logger.info("LiquidationMonitor started via WebSocket")
        await self._fetch_all_coins()
        while True:
            try:
                await self._connect()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"LiquidationMonitor reconnecting... ({e})")
                await asyncio.sleep(10)

    async def _fetch_all_coins(self):
        """Fetch semua perp coins dari HL API."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.post(HL_API_URL, json={"type": "metaAndAssetCtxs"}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list) and len(data) >= 1:
                            universe = data[0].get("universe", [])
                            self._perp_coins = [u["name"] for u in universe if "name" in u]
                            logger.info(f"LiquidationMonitor: {len(self._perp_coins)} perp coins")
        except Exception as e:
            logger.error(f"Coin fetch error: {e}")
            self._perp_coins = [
                "BTC", "ETH", "SOL", "BNB", "AVAX", "ARB", "OP",
                "DOGE", "LINK", "SUI", "APT", "HYPE", "WIF", "JTO",
            ]

    async def _connect(self):
        async with websockets.connect(HL_WS_URL, ping_interval=20, ping_timeout=10) as ws:
            # Subscribe ke semua perp coins
            for coin in self._perp_coins:
                sub = {
                    "method": "subscribe",
                    "subscription": {"type": "trades", "coin": coin}
                }
                await ws.send(json.dumps(sub))
                await asyncio.sleep(0.03)

            logger.info(f"LiquidationMonitor subscribed to {len(self._perp_coins)} coins")

            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    if msg.get("channel") == "trades":
                        data = msg.get("data", [])
                        if not isinstance(data, list):
                            data = [data]
                        for trade in data:
                            await self._handle_trade(trade)
                except Exception as e:
                    logger.debug(f"Parse error: {e}")

    async def _handle_trade(self, trade: dict):
        """
        Di Hyperliquid, liquidation trades punya field 'liquidation':
        {
          "liquidation": {
            "liquidatedUser": "0x...",
            "markPx": "79122.0",
            "method": "market"
          }
        }
        """
        liq_info = trade.get("liquidation")
        if not liq_info:
            return  # bukan liquidation trade

        tid = str(trade.get("tid") or trade.get("hash") or "")
        if tid and tid in self._seen_tids:
            return
        if tid:
            self._seen_tids.add(tid)

        # Data dari trade
        coin = trade.get("coin", "?")
        side = trade.get("side", "")  # B = long diliquidasi, A = short diliquidasi
        px = float(trade.get("px") or 0)
        sz = float(trade.get("sz") or 0)
        notional = px * sz

        if notional < LIQUIDATION_THRESHOLD_USD:
            return

        # Address yang kena liquidasi
        liquidated_user = liq_info.get("liquidatedUser", "")
        mark_px = float(liq_info.get("markPx") or px)

        # Side: kalau trade side B = liquidator beli = korban short
        #        kalau trade side A = liquidator jual = korban long
        position_side = "Short 🟢" if side == "B" else "Long 🔴"

        positions = [{
            "coin": coin,
            "szi": sz if side == "A" else -sz,
            "px": str(mark_px),
        }]

        msg = liquidation_alert(liquidated_user, notional, positions, f"{coin} {position_side} @ ${px:,.2f}")
        await self.grouper.add("Liquidations", msg)
        logger.info(f"Liquidation: {coin} {position_side} ${notional:,.0f} by {liquidated_user[:10]}...")

        # Cleanup
        if len(self._seen_tids) > 10000:
            self._seen_tids = set(list(self._seen_tids)[-5000:])