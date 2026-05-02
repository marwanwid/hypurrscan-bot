"""
config.py — All settings loaded from environment variables
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID: str = os.environ["TELEGRAM_CHAT_ID"]

# ── API URLs ─────────────────────────────────────────────────────────────────
HL_API_URL: str = "https://api.hyperliquid.xyz/info"
HL_WS_URL: str = "wss://api.hyperliquid.xyz/ws"
HYPURRSCAN_API_URL: str = "https://api.hypurrscan.io"

# ── Alert Thresholds ─────────────────────────────────────────────────────────
LIQUIDATION_THRESHOLD_USD: float = float(os.getenv("LIQUIDATION_THRESHOLD_USD", "1_000_000"))
TWAP_ALERT_THRESHOLD_USD: float = float(os.getenv("TWAP_ALERT_THRESHOLD_USD", "1_000_000"))
TWAP_DIGEST_THRESHOLD_USD: float = float(os.getenv("TWAP_DIGEST_THRESHOLD_USD", "500_000"))
SPOT_TRADE_THRESHOLD_USD: float = float(os.getenv("SPOT_TRADE_THRESHOLD_USD", "1_000_000"))
PERP_POSITION_THRESHOLD_USD: float = float(os.getenv("PERP_POSITION_THRESHOLD_USD", "10_000_000"))
OI_SPIKE_PERCENT: float = float(os.getenv("OI_SPIKE_PERCENT", "20"))
HYPE_STAKE_THRESHOLD: float = float(os.getenv("HYPE_STAKE_THRESHOLD", "100_000"))

# ── HYPE Price Alerts ────────────────────────────────────────────────────────
HYPE_PRICE_STEP: float = float(os.getenv("HYPE_PRICE_STEP", "5"))          # alert every $5
HYPE_SPIKE_PERCENT: float = float(os.getenv("HYPE_SPIKE_PERCENT", "5"))    # 5% spike
HYPE_SPIKE_WINDOW_MINUTES: int = int(os.getenv("HYPE_SPIKE_WINDOW_MINUTES", "15"))

# ── Whale Watchlist ──────────────────────────────────────────────────────────
WHALE_DEPOSIT_THRESHOLD_USD: float = float(os.getenv("WHALE_DEPOSIT_THRESHOLD_USD", "100_000"))
WHALE_WITHDRAW_THRESHOLD_USD: float = float(os.getenv("WHALE_WITHDRAW_THRESHOLD_USD", "100_000"))
WHALE_LIQUIDATION_THRESHOLD_USD: float = float(os.getenv("WHALE_LIQUIDATION_THRESHOLD_USD", "50_000"))

# ── Grouper ──────────────────────────────────────────────────────────────────
ALERT_GROUP_WINDOW_SECONDS: int = int(os.getenv("ALERT_GROUP_WINDOW_SECONDS", "30"))

# ── Polling Intervals (seconds) ───────────────────────────────────────────────
POLL_LIQUIDATION_SEC: int = int(os.getenv("POLL_LIQUIDATION_SEC", "30"))
POLL_TWAP_SEC: int = int(os.getenv("POLL_TWAP_SEC", "60"))
POLL_DEPLOYMENT_SEC: int = int(os.getenv("POLL_DEPLOYMENT_SEC", "60"))
POLL_OI_SEC: int = int(os.getenv("POLL_OI_SEC", "300"))   # 5 min
POLL_HYPE_PRICE_SEC: int = int(os.getenv("POLL_HYPE_PRICE_SEC", "10"))
POLL_WHALE_SEC: int = int(os.getenv("POLL_WHALE_SEC", "60"))

# ── Scheduler Intervals ───────────────────────────────────────────────────────
FEES_DIGEST_HOURS: int = int(os.getenv("FEES_DIGEST_HOURS", "6"))
TWAP_DIGEST_HOURS: int = int(os.getenv("TWAP_DIGEST_HOURS", "6"))

# ── Storage ───────────────────────────────────────────────────────────────────
WALLETS_FILE: str = os.getenv("WALLETS_FILE", "data/wallets.json")
