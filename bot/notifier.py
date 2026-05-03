"""
bot/notifier.py
Helper untuk kirim alert HTML langsung ke Telegram (bypass grouper).
Dipakai oleh OrderMonitor yang sudah punya dedup sendiri.
"""
import logging

from config import TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)


async def send_alert(bot, text: str):
    """Kirim pesan HTML ke TELEGRAM_CHAT_ID."""
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        log.error(f"send_alert failed: {e}")


def _fmt_usd(value: float) -> str:
    """Format angka ke string USD singkat (e.g. $5.20M, $300K)."""
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.2f}"
