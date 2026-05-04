"""
monitors/order_monitor.py
Detect large order accumulation via WS trades + REST confirmation.
- BTC >$5M, ETH >$3M, semua lain >$1M
- Agregasi dalam 10 menit window
- Konfirmasi posisi via REST setelah 5 detik
"""
import asyncio
import logging
import time
from collections import defaultdict

from telegram import Bot

from api.rest_client import get_clearinghouse_state
from api.ws_client import HyperliquidWS
from bot.notifier import send_alert, _fmt_usd
from db.database import list_wallets, is_alert_sent, mark_alert_sent

log = logging.getLogger(__name__)

BTC_THRESHOLD     = 5_000_000
ETH_THRESHOLD     = 3_000_000
DEFAULT_THRESHOLD = 1_000_000
CONFIRM_DELAY     = 5    # detik
WINDOW_SECONDS    = 600  # 10 menit


def get_threshold(coin: str) -> float:
    if coin == "BTC":
        return BTC_THRESHOLD
    elif coin == "ETH":
        return ETH_THRESHOLD
    return DEFAULT_THRESHOLD


class OrderMonitor:
    def __init__(self, ws: HyperliquidWS, bot: Bot):
        self._bot  = bot
        self._ws   = ws
        self._buffer: defaultdict  = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        self._position_cache: dict = {}
        self._pending: list        = []
        self._alerted: set         = set()
        ws.register("trades", self._handle_trade)
        log.info("OrderMonitor ready")

    async def subscribe_all_coins(self):
        try:
            from api.rest_client import get_meta
            meta  = await get_meta()
            coins = [u["name"] for u in meta.get("universe", [])]
            for coin in coins:
                self._ws.subscribe({"type": "trades", "coin": coin})
            log.info(f"OrderMonitor subscribed to {len(coins)} coins")
        except Exception as e:
            log.warning(f"subscribe_all_coins failed: {e}")

    async def run(self):
        while True:
            try:
                await self._process_pending()
            except Exception as e:
                log.exception(f"OrderMonitor run error: {e}")
            await asyncio.sleep(1)

    async def _handle_trade(self, msg: dict):
        trades = msg.get("data", [])
        if not isinstance(trades, list):
            trades = [trades]

        now_ms = int(time.time() * 1000)

        for trade in trades:
            try:
                # Skip liquidation trades — sudah dihandle LiquidationMonitor
                if trade.get("liquidation"):
                    continue

                coin     = trade.get("coin", "")
                side     = trade.get("side", "")   # "B" atau "A" (bukan "S"!)
                px       = float(trade.get("px") or 0)
                sz       = float(trade.get("sz") or 0)
                notional = px * sz
                t_ms     = int(trade.get("time") or now_ms)
                users    = trade.get("users") or []

                if notional < 10_000 or not users:
                    continue

                threshold = get_threshold(coin)

                # FIX: hanya proses address yang relevan dengan side-nya
                # users[0] = inisiator trade (taker)
                # users[1] = counterparty (maker)
                # Kita hanya track inisiator (index 0)
                addr = users[0] if users else ""
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
                # Key per window slot supaya tidak alert berkali-kali
                slot      = now_ms // (WINDOW_SECONDS * 1000)
                alert_key = f"order_{addr}_{coin}_{side}_{slot}"

                if total >= threshold and alert_key not in self._alerted:
                    self._alerted.add(alert_key)
                    confirm_at = time.time() + CONFIRM_DELAY
                    self._pending.append((confirm_at, addr, coin, side, total, count, alert_key))
                    self._buffer[addr][coin][side].clear()

            except Exception as e:
                log.debug(f"OrderMonitor trade parse: {e}")

        if len(self._alerted) > 10000:
            self._alerted = set(list(self._alerted)[-5000:])

    async def _process_pending(self):
        now = time.time()
        still_pending = []
        for item in self._pending:
            confirm_at, addr, coin, side, total_notional, count, alert_key = item
            if now < confirm_at:
                still_pending.append(item)
                continue
            try:
                await self._confirm_and_alert(addr, coin, side, total_notional, count, alert_key)
            except Exception as e:
                log.debug(f"confirm error: {e}")
        self._pending = still_pending

    async def _confirm_and_alert(self, address, coin, side, total_notional, count, alert_key):
        if await is_alert_sent(alert_key):
            return

        try:
            state     = await get_clearinghouse_state(address)
            positions = state.get("assetPositions", [])
        except Exception as e:
            log.debug(f"clearinghouseState error: {e}")
            return

        # Cari posisi coin ini
        current_pos = None
        for ap in positions:
            pos = ap.get("position", {})
            if pos.get("coin") == coin:
                szi = float(pos.get("szi") or 0)
                if szi != 0:
                    entry_px = float(pos.get("entryPx") or 0)
                    current_pos = {
                        "side":     "long" if szi > 0 else "short",
                        "szi":      szi,
                        "entry_px": entry_px,
                        "notional": abs(szi * entry_px),
                    }

        prev_pos = self._position_cache.get(address, {}).get(coin)

        # FIX: gunakan "A" bukan "S" untuk sell side
        action   = None
        entry_px = 0.0
        notional = total_notional

        if side == "B":  # Buy trade
            if current_pos and current_pos["side"] == "long":
                action   = "OPEN LONG"
                entry_px = current_pos["entry_px"]
                notional = current_pos["notional"]
            elif prev_pos and prev_pos["side"] == "short" and not current_pos:
                action = "CLOSE SHORT"
            else:
                action   = "OPEN LONG"
                entry_px = current_pos["entry_px"] if current_pos else 0

        elif side == "A":  # FIX: "A" bukan "S"
            if current_pos and current_pos["side"] == "short":
                action   = "OPEN SHORT"
                entry_px = current_pos["entry_px"]
                notional = current_pos["notional"]
            elif prev_pos and prev_pos["side"] == "long" and not current_pos:
                action = "CLOSE LONG"
            else:
                action   = "OPEN SHORT"
                entry_px = current_pos["entry_px"] if current_pos else 0

        if not action:
            return

        # Update position cache
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

        is_open  = "OPEN" in action
        is_long  = "LONG" in action
        emoji    = "🟢" if is_long else "🔴"
        lock     = "🔒" if is_open else "🔓"

        wallet_display = (
            f"<b>{label}</b> (<code>{address[:8]}...{address[-4:]}</code>)"
            if label else
            f"<a href='https://hypurrscan.io/address/{address}'>{address[:6]}...{address[-4:]}</a>"
        )

        entry_line = f"📈 Entry: ${entry_px:,.4f}\n" if entry_px > 0 else ""
        fills_line = f"📊 {count} fills dalam {WINDOW_SECONDS//60} menit\n" if count > 1 else ""

        text = (
            f"{emoji} <b>{lock} {action} — #{coin}</b>\n\n"
            f"💰 Notional: <b>{_fmt_usd(notional)}</b>\n"
            f"{entry_line}"
            f"{fills_line}"
            f"👤 {wallet_display}\n"
            f"🔗 <a href='https://hypurrscan.io/address/{address}'>HypurrScan</a>\n"
            f"🕐 {time.strftime('%H:%M:%S WIB', time.localtime(time.time() + 7*3600))}"
        )

        await send_alert(self._bot, text)
        await mark_alert_sent(alert_key)
        log.info(f"Order alert: {address[:10]} {action} #{coin} {_fmt_usd(notional)}")