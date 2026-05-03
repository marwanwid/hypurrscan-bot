"""
Hyperliquid Monitor Bot — Main Entry Point
Fixed for Python 3.12+ / 3.14 (no implicit event loop)
"""

import asyncio
import logging
import sys

from telegram.ext import Application

from config import TELEGRAM_BOT_TOKEN
from bot.commands import register_commands
from utils.grouper import AlertGrouper
from utils.storage import Storage
from monitors.liquidation_monitor import LiquidationMonitor
from monitors.twap_monitor import TWAPMonitor
from monitors.deployment_monitor import DeploymentMonitor
from monitors.oi_monitor import OIMonitor
from monitors.trade_monitor import TradeMonitor
from monitors.hype_monitor import HypeMonitor
from monitors.whale_monitor import WhaleMonitor
from monitors.order_monitor import OrderMonitor       # ← BARU
from schedulers.fees_scheduler import FeesScheduler
from api.ws_client import HyperliquidWS               # ← BARU
import db.database as db                              # ← BARU

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-25s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


async def main():
    storage = Storage()
    grouper = AlertGrouper()

    # ── Init shared WebSocket client ────────────────────────────────────────
    ws = HyperliquidWS()

    # ── Init in-memory database (dedup + wallet list) ───────────────────────
    db.init_db(storage)

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )
    app.bot_data["storage"] = storage
    app.bot_data["grouper"] = grouper

    register_commands(app)

    # Init TWAPMonitor dulu supaya bisa di-share ke TWAPDigestScheduler
    twap_monitor = TWAPMonitor(grouper)

    # Init OrderMonitor — butuh shared WS dan bot instance
    order_monitor = OrderMonitor(ws, app.bot)

    monitors = [
        LiquidationMonitor(grouper),
        twap_monitor,
        DeploymentMonitor(grouper),
        OIMonitor(grouper),
        TradeMonitor(grouper),
        HypeMonitor(grouper),
        WhaleMonitor(grouper, storage),
        FeesScheduler(grouper),
    ]

    logger.info("🤖 Hyperliquid Monitor Bot starting...")

    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("✅ Telegram polling started")

        # Subscribe OrderMonitor ke semua coins sebelum WS jalan
        await order_monitor.subscribe_all_coins()

        tasks = []

        # ── Task: shared WebSocket (untuk OrderMonitor) ──────────────────
        tasks.append(
            asyncio.create_task(ws.run(), name="HyperliquidWS")
        )
        logger.info("✅ Started: HyperliquidWS (shared)")

        # ── Task: OrderMonitor pending processor ─────────────────────────
        tasks.append(
            asyncio.create_task(order_monitor.run(), name="OrderMonitor")
        )
        logger.info("✅ Started: OrderMonitor")

        # ── Tasks: semua monitor lain ─────────────────────────────────────
        for monitor in monitors:
            task = asyncio.create_task(monitor.run(), name=monitor.__class__.__name__)
            tasks.append(task)
            logger.info(f"✅ Started: {monitor.__class__.__name__}")

        tasks.append(
            asyncio.create_task(grouper.flush_loop(app.bot), name="AlertGrouper")
        )
        logger.info("✅ Started: AlertGrouper")
        logger.info("🚀 All monitors running!")

        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("🛑 Shutdown signal received...")
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        await app.updater.stop()
        await app.stop()

    logger.info("👋 Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
