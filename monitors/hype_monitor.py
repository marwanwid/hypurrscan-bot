"""
monitors/hype_monitor.py
Monitors HYPE token:
  - Price milestone alerts every $5
  - Rapid spike/dump alert
  - Staking movement alert via validatorSummaries delta tracking
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


class HypeMonitor:
    def __init__(self, grouper: AlertGrouper):
        self.grouper = grouper
        self._current_price: Optional[float] = None
        self._alerted_levels: Set = set()
        self._price_history: deque = deque(maxlen=500)
        # Staking: track total stake per validator
        self._prev_validator_stakes: dict = {}  # validator_addr -> total_stake
        self._initialized_staking: bool = False

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
                logger.info(f"HYPE spike: {pct_change:+.2f}% in {HYPE_SPIKE_WINDOW_MINUTES}min")

    # ── Staking via validator total stake delta ───────────────────────────────

    async def _staking_poll_loop(self):
        await asyncio.sleep(10)
        while True:
            try:
                await self._check_staking()
            except Exception as e:
                logger.error(f"Staking poll error: {e}")
            await asyncio.sleep(30)

    async def _check_staking(self):
        """
        Track total stake per validator dari validatorSummaries.
        Kalau ada validator yang total stake-nya naik/turun >= HYPE_STAKE_THRESHOLD
        dalam satu poll window → ada yang stake/unstake besar.

        Catatan: kita tahu berapa HYPE yang di-stake/unstake dan ke validator mana,
        tapi tidak tahu wallet address spesifik siapa (limitasi API publik HL).
        """
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                async with session.post(
                    HL_API_URL,
                    json={"type": "validatorSummaries"}
                ) as resp:
                    if resp.status != 200:
                        logger.debug(f"validatorSummaries returned {resp.status}")
                        return
                    validators = await resp.json()

        except Exception as e:
            logger.debug(f"Staking fetch error: {e}")
            return

        if not isinstance(validators, list) or len(validators) == 0:
            return

        # Build current snapshot: validator_addr -> {name, stake}
        current_stakes = {}
        for v in validators:
            addr = v.get("validator") or v.get("address") or ""
            name = v.get("name") or v.get("moniker") or addr[:10]

            # Ambil stake — coba berbagai field name
            raw_stake = (
                v.get("totalStake") or
                v.get("stake") or
                v.get("votingPower") or
                v.get("stakedAmount") or 0
            )
            stake = float(raw_stake)

            # Auto-detect unit: kalau nilai sangat besar kemungkinan raw (1 HYPE = 1e8 atau 1e6)
            if stake > 1_000_000_000_000:  # > 1 Triliun → raw dengan 8 desimal
                stake = stake / 1e8
            elif stake > 1_000_000_000:    # > 1 Miliar → raw dengan 6 desimal
                stake = stake / 1e6

            if addr:
                current_stakes[addr] = {"name": name, "stake": stake}

        if not current_stakes:
            logger.debug("validatorSummaries returned empty data")
            return

        # First run — set baseline, jangan alert
        if not self._initialized_staking:
            self._prev_validator_stakes = current_stakes
            self._initialized_staking = True
            logger.info(f"Staking baseline set: {len(current_stakes)} validators, "
                        f"total staked: {sum(v['stake'] for v in current_stakes.values()):,.0f} HYPE")
            return

        # Compare — detect delta per validator
        for addr, data in current_stakes.items():
            prev = self._prev_validator_stakes.get(addr)
            if prev is None:
                # Validator baru muncul
                if data["stake"] >= HYPE_STAKE_THRESHOLD:
                    await self._send_staking_alert(
                        action="stake",
                        amount=data["stake"],
                        validator_name=data["name"],
                        validator_addr=addr,
                    )
                continue

            delta = data["stake"] - prev["stake"]

            if abs(delta) >= HYPE_STAKE_THRESHOLD:
                action = "stake" if delta > 0 else "unstake"
                await self._send_staking_alert(
                    action=action,
                    amount=abs(delta),
                    validator_name=data["name"],
                    validator_addr=addr,
                )
                logger.info(
                    f"Staking: {action} {abs(delta):,.0f} HYPE "
                    f"on validator {data['name']} ({addr[:10]}...)"
                )

        # Detect validator yang hilang dari list (full unstake semua delegator)
        for addr, prev_data in self._prev_validator_stakes.items():
            if addr not in current_stakes and prev_data["stake"] >= HYPE_STAKE_THRESHOLD:
                await self._send_staking_alert(
                    action="unstake",
                    amount=prev_data["stake"],
                    validator_name=prev_data["name"],
                    validator_addr=addr,
                )

        self._prev_validator_stakes = current_stakes

    async def _send_staking_alert(self, action: str, amount: float,
                                   validator_name: str, validator_addr: str):
        """Format dan kirim staking alert dengan info validator."""
        emoji = "🔒" if action == "stake" else "🔓"
        action_text = "STAKE" if action == "stake" else "UNSTAKE"

        # Format amount
        if amount >= 1_000_000:
            amount_str = f"{amount/1_000_000:.2f}M"
        elif amount >= 1_000:
            amount_str = f"{amount/1_000:.1f}K"
        else:
            amount_str = f"{amount:.0f}"

        short_addr = f"{validator_addr[:6]}...{validator_addr[-4:]}" if validator_addr else "Unknown"
        validator_link = f"[{short_addr}](https://hypurrscan.io/staking/{validator_addr})"

        from datetime import datetime, timezone, timedelta
        WIB = timezone(timedelta(hours=7))
        ts = datetime.now(WIB).strftime("%H:%M:%S WIB")

        text = (
            f"{emoji} *HYPE STAKING MOVEMENT*\n"
            f"Action: *{action_text}*\n"
            f"Amount: *{amount_str} HYPE*\n"
            f"Validator: *{validator_name}*\n"
            f"Val Address: {validator_link}\n"
            f"🕐 {ts}"
        )

        await self.grouper.add("HYPE Staking", text)