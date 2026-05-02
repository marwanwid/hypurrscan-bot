"""
Hyperliquid Monitor Bot — Main Entry Point
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
from schedulers.fees_scheduler import FeesScheduler
from schedulers.twap_digest_scheduler import TWAPDigestScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-25s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


def build_application() -> Application:
    return Application.builder().token(TELEGRAM_BOT_TOKEN).build()


async def post_init(application: Application) -> None:
    """Called after the bot starts — launch all monitors as background tasks."""
    storage: Storage = application.bot_data["storage"]
    grouper: AlertGrouper = application.bot_data["grouper"]

    monitors = [
        LiquidationMonitor(grouper),
        TWAPMonitor(grouper),
        DeploymentMonitor(grouper),
        OIMonitor(grouper),
        TradeMonitor(grouper),
        HypeMonitor(grouper),
        WhaleMonitor(grouper, storage),
        FeesScheduler(grouper),
        TWAPDigestScheduler(grouper),
    ]

    for monitor in monitors:
        asyncio.create_task(monitor.run(), name=monitor.__class__.__name__)
        logger.info(f"✅ Started: {monitor.__class__.__name__}")

    # Start the alert grouper flush loop
    asyncio.create_task(
        grouper.flush_loop(application.bot),
        name="AlertGrouper",
    )
    logger.info("✅ Started: AlertGrouper")
    logger.info("🚀 All monitors running!")


def main() -> None:
    storage = Storage()
    grouper = AlertGrouper()

    app = build_application()
    app.bot_data["storage"] = storage
    app.bot_data["grouper"] = grouper

    register_commands(app)

    app.post_init = post_init

    logger.info("🤖 Hyperliquid Monitor Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
