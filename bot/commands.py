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
        "I'm watching Hyperliquid 24/7 for:\n"
        "• 💀 Liquidations > $1M\n"
        "• 📊 Large TWAPs > $1M\n"
        "• 🪙 New token deployments\n"
        "• 📉 OI spikes > 20%\n"
        "• 🐋 Large trades\n"
        "• 💜 HYPE price milestones\n"
        "• 🔒 HYPE staking movements\n\n"
        "Use /help for all commands.",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ADMIN_COMMANDS, parse_mode="Markdown")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    storage: Storage = context.bot_data.get("storage")
    wallet_count = len(storage.get_wallets()) if storage else 0

    await update.message.reply_text(
        f"✅ *Bot Status: Running*\n\n"
        f"*Active Monitors:*\n"
        f"• 🚨 Liquidation Monitor (30s poll)\n"
        f"• 📊 TWAP Monitor (60s poll)\n"
        f"• 🪙 Deployment Monitor (60s poll)\n"
        f"• 📉 OI Spike Monitor (5min poll)\n"
        f"• 🐋 Trade Monitor (WebSocket)\n"
        f"• 💜 HYPE Monitor (WebSocket + 60s)\n"
        f"• 🔔 Whale Monitor ({wallet_count} wallets, 60s poll)\n\n"
        f"*Schedulers:*\n"
        f"• 📋 24H Fees Digest (every 6h)\n"
        f"• 📋 Active TWAP Digest (every 6h)\n\n"
        f"*Tracked Wallets:* {wallet_count}",
        parse_mode="Markdown",
    )


async def cmd_add_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    storage: Storage = context.bot_data.get("storage")
    args = context.args

    if not args:
        await update.message.reply_text(
            "Usage: `/addwallet <address> [label]`\n\n"
            "Example:\n"
            "`/addwallet 0xabc123... MyWhale`",
            parse_mode="Markdown",
        )
        return

    address = args[0].lower()
    label = " ".join(args[1:]) if len(args) > 1 else None

    if not address.startswith("0x") or len(address) < 10:
        await update.message.reply_text("❌ Invalid address format. Must start with 0x")
        return

    added = storage.add_wallet(address, label)
    short = f"{address[:6]}...{address[-4:]}"

    if added:
        await update.message.reply_text(
            f"✅ Wallet added to watchlist!\n"
            f"Address: `{short}`\n"
            f"Label: *{label or 'Unnamed'}*\n\n"
            f"I'll alert on deposits/withdrawals/liquidations.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(f"⚠️ Wallet `{short}` is already in the watchlist.", parse_mode="Markdown")


async def cmd_remove_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    storage: Storage = context.bot_data.get("storage")
    args = context.args

    if not args:
        await update.message.reply_text("Usage: `/removewallet <address>`", parse_mode="Markdown")
        return

    address = args[0].lower()
    removed = storage.remove_wallet(address)
    short = f"{address[:6]}...{address[-4:]}"

    if removed:
        await update.message.reply_text(f"✅ Removed `{short}` from watchlist.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Wallet `{short}` not found in watchlist.", parse_mode="Markdown")


async def cmd_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    storage: Storage = context.bot_data.get("storage")
    wallets = storage.get_wallets()

    if not wallets:
        await update.message.reply_text(
            "📋 No wallets tracked yet.\n\nUse `/addwallet <address> [label]` to add one.",
            parse_mode="Markdown",
        )
        return

    lines = ["📋 *Tracked Wallets:*\n"]
    for i, (addr, meta) in enumerate(wallets.items(), 1):
        short = f"{addr[:6]}...{addr[-4:]}"
        label = meta.get("label", "Unnamed")
        lines.append(f"{i}. *{label}* — `{short}`")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
