"""
bot/commands.py — All Telegram bot commands
"""

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from utils.storage import Storage

logger = logging.getLogger(__name__)

ADMIN_COMMANDS = """
🤖 *Hyperliquid Monitor Bot*

*Wallet Watchlist:*
/addwallet `<address> [label]` — Add wallet to watchlist
/removewallet `<address>` — Remove wallet from watchlist
/wallets — List all tracked wallets

*Info:*
/status — Bot status & active monitors
/help — Show this message

_Bot alerts automatically to this chat._
"""


def register_commands(app: Application):
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("addwallet", cmd_add_wallet))
    app.add_handler(CommandHandler("removewallet", cmd_remove_wallet))
    app.add_handler(CommandHandler("wallets", cmd_wallets))


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 *Hyperliquid Monitor Bot is running!*\n\n"
        "Monitoring Hyperliquid 24/7 untuk:\n\n"
        "*Real-time alerts:*\n"
        "• 🚨 Liquidation completed >$100K\n"
        "• 📊 Large TWAP order >$1M\n"
        "• 🐋 Large perp trade >$1M\n"
        "• 💰 Large spot trade >$1M\n"
        "• 🪙 New token deployment\n"
        "• 📉 OI spike >20%\n"
        "• 💜 HYPE price milestone (tiap $5)\n"
        "• ⚡ HYPE spike/dump >5% dalam 15 menit\n"
        "• 🔒 HYPE stake/unstake >100K\n"
        "• 🐳 Whale watchlist (deposit/withdraw/liq >$100K)\n\n"
        "*Scheduled:*\n"
        "• 📊 24H Fees Digest (tiap 1 jam)\n\n"
        "Ketik /help untuk semua commands.",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ADMIN_COMMANDS, parse_mode="Markdown")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    storage: Storage = context.bot_data.get("storage")
    wallet_count = len(storage.get_wallets()) if storage else 0

    await update.message.reply_text(
        f"✅ *Bot Status: Running*\n\n"
        f"*Real-time Monitors (WebSocket):*\n"
        f"• 🚨 Liquidation Monitor — semua perp\n"
        f"• 📊 TWAP Monitor — semua pair\n"
        f"• 🐋 Trade Monitor — semua perp + spot\n"
        f"• 💜 HYPE Price Monitor\n"
        f"• 📈 Order Monitor — BTC >$5M, ETH >$3M, lain >$1M\n\n"
        f"*Poll-based Monitors:*\n"
        f"• 🪙 Deployment Monitor (60s)\n"
        f"• 📉 OI Spike Monitor (5 menit)\n"
        f"• 🔒 HYPE Staking Monitor (30s)\n"
        f"• 🐳 Whale Watchlist ({wallet_count} wallets, 60s)\n\n"
        f"*Schedulers:*\n"
        f"• 📊 24H Fees Digest (tiap 1 jam)\n\n"
        f"*Tracked Wallets:* {wallet_count}\n\n"
        f"*Thresholds:*\n"
        f"• Liquidation: >$100K\n"
        f"• TWAP: >$1M\n"
        f"• Perp/Spot trade: >$1M\n"
        f"• HYPE staking: >100K HYPE",
        parse_mode="Markdown",
    )


async def cmd_add_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    storage: Storage = context.bot_data.get("storage")
    args = context.args

    if not args:
        await update.message.reply_text(
            "Usage: `/addwallet <address> [label]`\n\n"
            "Contoh:\n"
            "`/addwallet 0xabc123... BigWhale`",
            parse_mode="Markdown",
        )
        return

    address = args[0].lower()
    label = " ".join(args[1:]) if len(args) > 1 else None

    if not address.startswith("0x") or len(address) < 10:
        await update.message.reply_text("❌ Format address salah. Harus diawali 0x")
        return

    added = storage.add_wallet(address, label)
    short = f"{address[:6]}...{address[-4:]}"

    if added:
        await update.message.reply_text(
            f"✅ Wallet ditambahkan ke watchlist!\n"
            f"Address: `{short}`\n"
            f"Label: *{label or 'Unnamed'}*\n\n"
            f"Bot akan alert kalau ada deposit/withdraw/liquidasi >$100K.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            f"⚠️ Wallet `{short}` sudah ada di watchlist.",
            parse_mode="Markdown",
        )


async def cmd_remove_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    storage: Storage = context.bot_data.get("storage")
    args = context.args

    if not args:
        await update.message.reply_text(
            "Usage: `/removewallet <address>`",
            parse_mode="Markdown",
        )
        return

    address = args[0].lower()
    removed = storage.remove_wallet(address)
    short = f"{address[:6]}...{address[-4:]}"

    if removed:
        await update.message.reply_text(
            f"✅ `{short}` dihapus dari watchlist.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            f"❌ Wallet `{short}` tidak ditemukan di watchlist.",
            parse_mode="Markdown",
        )


async def cmd_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    storage: Storage = context.bot_data.get("storage")
    wallets = storage.get_wallets()

    if not wallets:
        await update.message.reply_text(
            "📋 Belum ada wallet yang ditrack.\n\n"
            "Gunakan `/addwallet <address> [label]` untuk menambah.",
            parse_mode="Markdown",
        )
        return

    lines = ["📋 *Tracked Wallets:*\n"]
    for i, (addr, meta) in enumerate(wallets.items(), 1):
        short = f"{addr[:6]}...{addr[-4:]}"
        label = meta.get("label", "Unnamed")
        lines.append(f"{i}. *{label}* — `{short}`")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")