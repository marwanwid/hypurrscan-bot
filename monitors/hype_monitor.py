"""
monitors/hype_monitor.py
Monitors HYPE token:
  - Price milestone alerts every $5 (30, 35, 40, ...)
  - Rapid spike/dump alert (>5% in X minutes)
  - Staking movement alert (stake/unstake > 100K HYPE) per address
"""

import asyncio
import json
import logging
import time
from collections import deque
from typing import Optional, Set

import aiohttp
import websockets

from config import (
    HL_API_URL,
    HL_WS_URL,
    HYPE_PRICE_STEP,
    HYPE_SPIKE_PERCENT,
    HYPE_SPIKE_WINDOW_MINUTES,
    HYPE_STAKE_THRESHOLD,
)
from utils.formatter import hype_price_level_alert, hype_spike_alert, hype_staking_alert
from utils.grouper import AlertGrouper

logger = logging.getLogger(__name__)

HYPE_DECIMALS = 1_000_000


class HypeMonitor:
    def __init__(self, grouper: AlertGrouper):
        self.grouper = grouper
        self._current_price: Optional[float] = None
        self._alerted_levels: Set = set()
        self._price_history: deque = deque(maxlen=500)
        self._last_stake_snapshot: dict = {}

    async def run(self):
        logger.info("HypeMonitor started")
        await asyncio.gather(
            self._price_ws_loop(),
            self._staking_poll_loop(),
        )

    # ── Price via WebSocket ──────────────────────────────────────────────────

    async def _price_ws_loop(self):
        while True:
            try:
                await self._connect_price_ws()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"HYPE price WS error: {e} — reconnecting in 15s")
                await asyncio.sleep(15)

    async def _connect_price_ws(self):
        async with websockets.connect(HL_WS_URL, ping_interval=20) as ws:
            sub = {"method": "subscribe", "subscription": {"type": "allMids"}}
            await ws.send(json.dumps(sub))
            logger.info("Subscribed to allMids for HYPE price")

            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    if msg.get("channel") == "allMids":
                        mids = msg.get("data", {}).get("mids", {})
                        hype_price = mids.get("HYPE") or mids.get("@HYPE")
                        if hype_price:
                            await self._handle_price(float(hype_price))
                except Exception as e:
                    logger.debug(f"Price parse error: {e}")

    async def _handle_price(self, price: float):
        now = time.time()
        self._price_history.append((now, price))
        self._current_price = price
        await self._check_price_levels(price)
        await self._check_spike(price, now)

    async def _check_price_levels(self, price: float):
        step = HYPE_PRICE_STEP
        level = round((price // step) * step, 2)
        if level > 0 and level not in self._alerted_levels:
            if abs(price - level) < 0.5 or price > level:
                self._alerted_levels.add(level)
                msg = hype_price_level_alert(price, level)
                await self.grouper.add("HYPE Price", msg)
                logger.info(f"HYPE price milestone: ${level} (current: ${price:.2f})")

    async def _check_spike(self, current_price: float, now: float):
        window_sec = HYPE_SPIKE_WINDOW_MINUTES * 60
        cutoff = now - window_sec
        baseline_price = None
        for ts, px in self._price_history:
            if ts >= cutoff:
                baseline_price = px
                break
        if baseline_price is None or baseline_price == 0:
            return
        pct_change = ((current_price - baseline_price) / baseline_price) * 100
        if abs(pct_change) >= HYPE_SPIKE_PERCENT:
            cooldown_key = f"spike_{round(now / 300)}"
            if cooldown_key not in self._alerted_levels:
                self._alerted_levels.add(cooldown_key)
                msg = hype_spike_alert(current_price, baseline_price, pct_change, HYPE_SPIKE_WINDOW_MINUTES)
                await self.grouper.add("HYPE Spike", msg)
                logger.info(f"HYPE spike detected: {pct_change:+.2f}% in {HYPE_SPIKE_WINDOW_MINUTES}min")

    # ── Staking via REST poll ────────────────────────────────────────────────

    async def _staking_poll_loop(self):
        await asyncio.sleep(10)
        while True:
            try:
                await self._check_staking()
            except Exception as e:
                logger.error(f"Staking poll error: {e}")
            await asyncio.sleep(60)

    async def _check_staking(self):
        """
        Track individual delegator stake changes per validator.
        Alert kalau ada address yang stake/unstake > HYPE_STAKE_THRESHOLD.
        """
        # Step 1: ambil list semua validator
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.post(HL_API_URL, json={"type": "validatorSummaries"}) as resp:
                    if resp.status != 200:
                        return
                    validators = await resp.json()
        except Exception as e:
            logger.debug(f"Staking fetch error: {e}")
            return

        if not isinstance(validators, list):
            return

        # Step 2: untuk setiap validator, ambil delegator list
        current_snapshot = {}

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                for v in validators:
                    validator_addr = v.get("validator") or v.get("address") or ""
                    if not validator_addr:
                        continue
                    try:
                        async with session.post(
                            HL_API_URL,
                            json={"type": "delegations", "validator": validator_addr}
                        ) as resp:
                            if resp.status != 200:
                                continue
                            delegations = await resp.json()
                    except Exception:
                        continue

                    if not isinstance(delegations, list):
                        continue

                    for d in delegations:
                        user_addr = d.get("delegator") or d.get("user") or d.get("address") or ""
                        raw_amount = float(d.get("amount") or d.get("stake") or d.get("stakedAmount") or 0)
                        normalized = raw_amount / HYPE_DECIMALS

                        if user_addr:
                            key = f"{user_addr}_{validator_addr}"
                            current_snapshot[key] = {
                                "user": user_addr,
                                "validator": validator_addr,
                                "amount": normalized,
                            }

                    await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Delegations fetch error: {e}")
            return

        # Step 3: compare, detect perubahan individual
        if not self._last_stake_snapshot:
            self._last_stake_snapshot = current_snapshot
            logger.info(f"Staking baseline set: {len(current_snapshot)} delegator-validator pairs")
            return

        for key, data in current_snapshot.items():
            old_data = self._last_stake_snapshot.get(key)
            old_amount = old_data["amount"] if old_data else 0.0
            new_amount = data["amount"]
            delta = new_amount - old_amount

            if abs(delta) >= HYPE_STAKE_THRESHOLD:
                action = "stake" if delta > 0 else "unstake"
                msg = hype_staking_alert(action, abs(delta), data["user"])
                await self.grouper.add("HYPE Staking", msg)
                logger.info(
                    f"Staking: {action} {abs(delta):,.0f} HYPE "
                    f"by {data['user'][:10]}..."
                )

        # Detect full unstake (delegator keluar dari list)
        for key, old_data in self._last_stake_snapshot.items():
            if key not in current_snapshot and old_data["amount"] >= HYPE_STAKE_THRESHOLD:
                msg = hype_staking_alert("unstake", old_data["amount"], old_data["user"])
                await self.grouper.add("HYPE Staking", msg)
                logger.info(f"Full unstake: {old_data['amount']:,.0f} HYPE by {old_data['user'][:10]}...")

        self._last_stake_snapshot = current_snapshot