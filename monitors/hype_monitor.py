"""
monitors/hype_monitor.py
Monitors HYPE token:
  - Price milestone alerts every $5 (30, 35, 40, ...)
  - Rapid spike/dump alert (>5% in X minutes)
  - Staking movement alert (stake/unstake > 100K HYPE)
"""

import asyncio
import json
import logging
import time
from collections import deque
from typing import Optional, Set

import websockets

from config import (
    HL_WS_URL,
    HYPE_PRICE_STEP,
    HYPE_SPIKE_PERCENT,
    HYPE_SPIKE_WINDOW_MINUTES,
    HYPE_STAKE_THRESHOLD,
    POLL_HYPE_PRICE_SEC,
)
from utils.formatter import hype_price_level_alert, hype_spike_alert, hype_staking_alert
from utils.grouper import AlertGrouper

logger = logging.getLogger(__name__)


class HypeMonitor:
    def __init__(self, grouper: AlertGrouper):
        self.grouper = grouper
        self._current_price: Optional[float] = None
        self._alerted_levels: Set[float] = set()
        self._price_history: deque = deque(maxlen=500)  # (timestamp, price)
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
        """Alert when HYPE crosses each $5 milestone."""
        step = HYPE_PRICE_STEP
        # Find which milestone we're at or above
        level = round((price // step) * step, 2)
        if level > 0 and level not in self._alerted_levels:
            # Check if we just crossed this level (price is within $0.5 of the level)
            if abs(price - level) < 0.5 or price > level:
                self._alerted_levels.add(level)
                msg = hype_price_level_alert(price, level)
                await self.grouper.add("HYPE Price", msg)
                logger.info(f"HYPE price milestone: ${level} (current: ${price:.2f})")

    async def _check_spike(self, current_price: float, now: float):
        """Alert if HYPE moves >5% within HYPE_SPIKE_WINDOW_MINUTES."""
        window_sec = HYPE_SPIKE_WINDOW_MINUTES * 60
        cutoff = now - window_sec

        # Find oldest price within the window
        baseline_price = None
        for ts, px in self._price_history:
            if ts >= cutoff:
                baseline_price = px
                break

        if baseline_price is None or baseline_price == 0:
            return

        pct_change = ((current_price - baseline_price) / baseline_price) * 100
        if abs(pct_change) >= HYPE_SPIKE_PERCENT:
            # Cooldown: only alert once per 5 minutes for spikes
            cooldown_key = f"spike_{round(now / 300)}"
            if cooldown_key not in self._alerted_levels:
                self._alerted_levels.add(cooldown_key)
                msg = hype_spike_alert(current_price, baseline_price, pct_change, HYPE_SPIKE_WINDOW_MINUTES)
                await self.grouper.add("HYPE Spike", msg)
                logger.info(f"HYPE spike detected: {pct_change:+.2f}% in {HYPE_SPIKE_WINDOW_MINUTES}min")

    # ── Staking via REST poll ────────────────────────────────────────────────

    async def _staking_poll_loop(self):
        """Poll staking/delegation data every 60 seconds."""
        await asyncio.sleep(10)  # stagger vs price WS
        while True:
            try:
                await self._check_staking()
            except Exception as e:
                logger.error(f"Staking poll error: {e}")
            await asyncio.sleep(60)

    async def _check_staking(self):
        """
        Fetch validator delegations and detect large stake/unstake movements.
        Uses Hyperliquid's delegatorSummary and validatorSummaries endpoints.
        """
        import aiohttp
        from config import HL_API_URL

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

        # Build current snapshot: validator -> totalStake
        current_snapshot = {}
        for v in validators:
            vid = v.get("validator") or v.get("address") or ""
            stake = float(v.get("totalStake") or v.get("stake") or v.get("jailDetails", {}).get("totalStake") or 0)
            if vid:
                current_snapshot[vid] = stake

        if not self._last_stake_snapshot:
            self._last_stake_snapshot = current_snapshot
            return

        # Detect changes
        for vid, new_stake in current_snapshot.items():
            old_stake = self._last_stake_snapshot.get(vid, new_stake)
            delta = new_stake - old_stake
            if abs(delta) >= HYPE_STAKE_THRESHOLD:
                action = "stake" if delta > 0 else "unstake"
                msg = hype_staking_alert(action, abs(delta), vid)
                await self.grouper.add("HYPE Staking", msg)
                logger.info(f"Staking movement: {action} {abs(delta):,.0f} HYPE on {vid[:10]}...")

        self._last_stake_snapshot = current_snapshot
