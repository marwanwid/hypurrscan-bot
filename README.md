# 🤖 Hyperliquid Monitor Bot

Telegram bot yang memonitor Hyperliquid 24/7 dan mengirimkan notifikasi real-time.

## 📋 Features

| Feature | Trigger |
|---------|---------|
| 💀 Liquidation Alert | Liquidasi address > $1M |
| 📊 TWAP Alert | TWAP baru > $1M notional (via WebSocket) |
| 🪙 Deployment Alert | Token spot/perp baru deploy |
| 📉 OI Spike | Open Interest naik/turun >20% dalam 5 menit |
| 🐋 Large Perp Trade | Posisi perp dibuka >$10M |
| 💰 Large Spot Trade | Transaksi spot >$1M |
| 💜 HYPE Price Level | HYPE sentuh $30, $35, $40, $45... |
| ⚡ HYPE Spike | HYPE naik/turun >5% dalam 15 menit |
| 🔒 HYPE Staking | Stake/unstake >100K HYPE |
| 📥 Whale Deposit | Watchlist address deposit >$100K |
| 📤 Whale Withdraw | Watchlist address withdraw >$100K |
| 📋 Fees Digest | 24H protocol fees (setiap 6 jam) |
| 📋 TWAP Digest | Active TWAP >$500K (setiap 6 jam) |

## 🚀 Quick Setup

### 1. Buat Telegram Bot
1. Chat ke [@BotFather](https://t.me/BotFather)
2. Ketik `/newbot`
3. Copy token yang dikasih

### 2. Dapatkan Chat ID
1. Add bot ke group/channel lu
2. Chat ke [@getidsbot](https://t.me/getidsbot) di dalam group
3. Copy chat ID (biasanya negatif, e.g. `-1001234567890`)

### 3. Clone & Setup
```bash
git clone https://github.com/marwanwid/hypurrscan-bot.git
cd hypurrscan-bot
cp .env.example .env
# Edit .env dan isi TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID
```

### 4. Test Locally
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 🚂 Deploy ke Railway

1. Buka [railway.app](https://railway.app) → Login with GitHub
2. New Project → Deploy from GitHub repo → pilih `hypurrscan-bot`
3. Pergi ke tab **Variables**, tambahkan:
   - `TELEGRAM_BOT_TOKEN` = token dari BotFather
   - `TELEGRAM_CHAT_ID` = chat ID group lu
4. Railway auto-deploy ✅

## 🤖 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | List semua commands |
| `/status` | Status bot dan monitors |
| `/addwallet 0x... Label` | Tambah wallet ke watchlist |
| `/removewallet 0x...` | Hapus wallet dari watchlist |
| `/wallets` | List semua wallet yang ditrack |

## ⚙️ Konfigurasi Threshold

Edit `.env` atau set di Railway environment variables:

```env
LIQUIDATION_THRESHOLD_USD=1000000    # Alert liquidasi >$1M
PERP_POSITION_THRESHOLD_USD=10000000 # Alert perp trade >$10M
SPOT_TRADE_THRESHOLD_USD=1000000     # Alert spot trade >$1M
HYPE_PRICE_STEP=5                    # Alert tiap $5 milestone
HYPE_SPIKE_PERCENT=5                 # Alert kalau HYPE spike >5%
HYPE_SPIKE_WINDOW_MINUTES=15         # Window spike detection
HYPE_STAKE_THRESHOLD=100000          # Alert stake/unstake >100K HYPE
FEES_DIGEST_HOURS=6                  # Kirim fees digest tiap 6 jam
```

## 🏗️ Architecture