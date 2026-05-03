"""
monitors/order_monitor.py
Gabungan WS trades + REST konfirmasi untuk detect:
- Open Long / Open Short
- Close Long / Close Short
Threshold: BTC >$5M, semua lain >$1M
"""
import asyncio
import logging
import time
from collections import defaultdict

from telegram import Bot

import config
from api.rest_client import get_clearinghouse_state
from api.ws_client import HyperliquidWS
from bot.notifier import send_alert, _fmt_usd
from db.database import list_wallets, is_alert_sent, mark_alert_sent

log = logging.getLogger(__name__)

# Threshold per coin
BTC_THRESHOLD     = 5_000_000   # $5M
DEFAULT_THRESHOLD = 1_000_000   # $1M

# Seberapa lama tunggu konfirmasi REST setelah WS trade
CONFIRM_DELAY = 5   # detik

# Rolling window untuk agregasi order per address
WINDOW_SECONDS = 600  # 10 menit


def get_threshold(coin: str) -> float:
    if coin == "BTC":
        return BTC_THRESHOLD
    return DEFAULT_THRESHOLD


class OrderMonitor:
    def __init__(self, ws: HyperliquidWS, bot: Bot):
        self._bot = bot
        self._ws  = ws

        # Buffer agregasi: address → coin → side → [(time_ms, notional)]
        self._buffer: defaultdict = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )

        # Cache posisi terakhir per address: address → {coin → {side, notional}}
        self._position_cache: dict[str, dict] = {}

        # Queue konfirmasi pending: [(confirm_at, address, coin, side, total_notional, trade_count)]
        self._pending: list[tuple] = []

        # Alerted set untuk dedup dalam window
        self._alerted: set[str] = set()

        # Subscribe semua coin
        ws.register("trades", self._handle_trade)

        log.info(f"OrderMonitor ready — "
                 f"BTC >$5M, others >$1M, confirm delay {CONFIRM_DELAY}s")

    async def subscribe_all_coins(self):
        """Subscribe ke semua perp coins dari HL meta API."""
        try:
            from api.rest_client import get_meta
            meta  = await get_meta()
            coins = [u["name"] for u in meta.get("universe", [])]
            for coin in coins:
                self._ws.subscribe({"type": "trades", "coin": coin})
            log.info(f"OrderMonitor: subscribed to {len(coins)} coins")
        except Exception as e:
            log.warning(f"subscribe_all_coins failed: {e}")

    async def run(self):
        """Proses pending konfirmasi secara berkala."""
        while True:
            try:
                await self._process_pending()
            except Exception as e:
                log.exception(f"OrderMonitor run error: {e}")
            await asyncio.sleep(1)

    # ── WS Handler ────────────────────────────────────────────────────────────

    async def _handle_trade(self, msg: dict):
        trades = msg["data"]
        if not isinstance(trades, list):
            trades = [trades]

        now_ms = int(time.time() * 1000)

        for trade in trades:
            try:
                # Skip liquidation trades
                if trade.get("liquidation"):
                    continue

                coin     = trade.get("coin", "")
                side     = trade.get("side", "")
                px       = float(trade.get("px", 0))
                sz       = float(trade.get("sz", 0))
                notional = px * sz
                t_ms     = int(trade.get("time", now_ms))
                users    = trade.get("users", [])

                if notional < 10_000 or not users:
                    continue

                threshold = get_threshold(coin)

                for addr in users:
                    if not addr or not addr.startswith("0x"):
                        continue
                    addr = addr.lower()

                    # Agregasi ke buffer
                    bucket = self._buffer[addr][coin][side]
                    cutoff = now_ms - (WINDOW_SECONDS * 1000)
                    bucket[:] = [(t, n) for t, n in bucket if t >= cutoff]
                    bucket.append((t_ms, notional))

                    total     = sum(n for _, n in bucket)
                    count     = len(bucket)
                    alert_key = f"order_{addr}_{coin}_{side}_{now_ms // (WINDOW_SECONDS * 1000)}"

                    if total >= threshold and alert_key not in self._alerted:
                        self._alerted.add(alert_key)
                        # Queue untuk konfirmasi REST setelah delay
                        confirm_at = time.time() + CONFIRM_DELAY
                        self._pending.append((
                            confirm_at, addr, coin, side, total, count, alert_key
                        ))
                        # Clear buffer setelah queue
                        self._buffer[addr][coin][side].clear()

            except Exception as e:
                log.debug(f"OrderMonitor trade parse: {e}")

    # ── REST Konfirmasi ───────────────────────────────────────────────────────

    async def _process_pending(self):
        now = time.time()
        still_pending = []

        for item in self._pending:
            confirm_at, addr, coin, side, total_notional, count, alert_key = item

            if now < confirm_at:
                still_pending.append(item)
                continue

            # Waktunya konfirmasi
            try:
                await self._confirm_and_alert(
                    addr, coin, side, total_notional, count, alert_key
                )
            except Exception as e:
                log.debug(f"confirm error: {e}")

        self._pending = still_pending

    async def _confirm_and_alert(self, address: str, coin: str, side: str,
                                  total_notional: float, count: int, alert_key: str):
        """Konfirmasi via REST lalu tentukan open/close."""
        if await is_alert_sent(alert_key):
            return

        # Fetch posisi sekarang
        try:
            state     = await get_clearinghouse_state(address)
            positions = state.get("assetPositions", [])
        except Exception as e:
            log.debug(f"clearinghouseState({address}): {e}")
            return

        # Cari posisi untuk coin ini
        current_pos = None
        for ap in positions:
            pos  = ap.get("position", {})
            if pos.get("coin") == coin:
                szi = float(pos.get("szi", 0) or 0)
                if szi != 0:
                    current_pos = {
                        "side":     "long" if szi > 0 else "short",
                        "szi":      szi,
                        "entry_px": float(pos.get("entryPx", 0) or 0),
                        "notional": abs(szi * float(pos.get("entryPx", 0) or 0)),
                    }

        # Bandingkan dengan cache untuk tentukan open/close
        prev_pos = self._position_cache.get(address, {}).get(coin)

        # Tentukan action
        action     = None
        pos_side   = None
        notional   = total_notional
        entry_px   = 0.0

        if side == "B":
            # Buy trade → Open Long atau Close Short
            if current_pos and current_pos["side"] == "long":
                action   = "OPEN LONG"
                pos_side = "long"
                entry_px = current_pos["entry_px"]
                notional = current_pos["notional"]
            elif prev_pos and prev_pos["side"] == "short" and not current_pos:
                action   = "CLOSE SHORT"
                pos_side = "short"
                notional = total_notional
            else:
                action   = "OPEN LONG"
                pos_side = "long"
                entry_px = current_pos["entry_px"] if current_pos else 0

        elif side == "S":
            # Sell trade → Open Short atau Close Long
            if current_pos and current_pos["side"] == "short":
                action   = "OPEN SHORT"
                pos_side = "short"
                entry_px = current_pos["entry_px"]
                notional = current_pos["notional"]
            elif prev_pos and prev_pos["side"] == "long" and not current_pos:
                action   = "CLOSE LONG"
                pos_side = "long"
                notional = total_notional
            else:
                action   = "OPEN SHORT"
                pos_side = "short"
                entry_px = current_pos["entry_px"] if current_pos else 0

        if not action:
            return

        # Update cache
        if address not in self._position_cache:
            self._position_cache[address] = {}
        if current_pos:
            self._position_cache[address][coin] = current_pos
        elif coin in self._position_cache.get(address, {}):
            del self._position_cache[address][coin]

        # Cari label kalau wallet ditrack
        wallets    = await list_wallets()
        wallet_map = {w["address"]: w.get("label", "") for w in wallets}
        label      = wallet_map.get(address, "")

        # Format alert
        is_open    = "OPEN" in action
        is_long    = "LONG" in action
        side_emoji = "🟢" if is_long else "🔴"

        wallet_display = (
            f"<b>{label}</b> (<code>{address[:8]}...{address[-4:]}</code>)"
            if label else f"<code>{address}</code>"
        )

        entry_line = f"📈 Entry: ${entry_px:,.4f}\n" if entry_px > 0 else ""
        fills_line = f"📊 {count} fills dalam {WINDOW_SECONDS//60}min\n" if count > 1 else ""

        text = (
            f"{side_emoji} <b>{'🔓' if not is_open else '🔒'} {action} — #{coin}</b>\n\n"
            f"{side_emoji} #{coin} <b>{action}</b>\n"
            f"💰 Notional: <b>{_fmt_usd(notional)}</b>\n"
            f"{entry_line}"
            f"{fills_line}"
            f"👤 {wallet_display}\n"
            f"🔗 <a href='https://hypurrscan.io/address/{address}'>HypurrScan</a>"
        )

        await send_alert(self._bot, text)
        await mark_alert_sent(alert_key)
        log.info(f"Order confirmed: {address} {action} #{coin} {_fmt_usd(notional)}")
