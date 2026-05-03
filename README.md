# 🤖 Hyperliquid Monitor Bot

Telegram bot yang memonitor Hyperliquid 24/7 dan mengirimkan notifikasi real-time.

## 📋 Features

| Feature | Trigger |
|---------|---------|
| 🚨 Liquidation Alert | Liquidasi completed >$100K (semua market) |
| 📊 TWAP Alert | TWAP order >$1M notional (semua pair) |
| 🐋 Large Perp Trade | Trade perp >$1M (semua coin) |
| 💰 Large Spot Trade | Trade spot >$1M (semua token) |
| 📈 Order Accumulation | BTC >$5M / ETH >$3M / lain >$1M dalam 10 menit |
| 🪙 New Deployment | Token spot atau perp HIP-3 baru |
| 📉 OI Spike | Open Interest naik/turun >20% |
| 💜 HYPE Price Milestone | HYPE sentuh $30, $35, $40, $45... |
| ⚡ HYPE Spike/Dump | HYPE naik/turun >5% dalam 15 menit |
| 🔒 HYPE Staking | Stake/unstake >100K HYPE per address |
| 🐳 Whale Watchlist | Deposit/withdraw/liquidasi >$100K |
| 📊 Fees Digest | 24H protocol fees (tiap 1 jam) |

## 🚀 Quick Setup

### 1. Buat Telegram Bot
1. Chat ke [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy token yang dikasih

### 2. Dapatkan Chat ID
1. Add bot ke group/channel
2. Chat ke [@getidsbot](https://t.me/getidsbot) di dalam group
3. Copy chat ID (angka negatif, e.g. `-1001234567890`)

### 3. Clone & Setup
```bash
git clone https://github.com/marwanwid/hypurrscan-bot.git
cd hypurrscan-bot
cp .env.example .env
# Edit .env — isi TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID
pip install -r requirements.txt
python main.py
```

## 🚂 Deploy ke Railway

1. [railway.app](https://railway.app) → Login with GitHub
2. New Project → Deploy from GitHub → pilih repo
3. Tab **Variables** → paste raw config (lihat `.env.example`)
4. Auto-deploy ✅

## 🤖 Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome + list semua fitur |
| `/help` | List commands |
| `/status` | Status semua monitor + threshold |
| `/addwallet 0x... Label` | Tambah wallet ke watchlist |
| `/removewallet 0x...` | Hapus wallet dari watchlist |
| `/wallets` | List semua wallet yang ditrack |

## 🏗️ Architecture

```
main.py                        ← Entry point
config.py                      ← Settings dari .env
api/
├── ws_client.py               ← Shared WebSocket client
└── rest_client.py             ← REST helpers
monitors/
├── liquidation_monitor.py     ← WS real-time liquidations
├── twap_monitor.py            ← WS real-time TWAP fills
├── trade_monitor.py           ← WS real-time large trades
├── order_monitor.py           ← WS + REST order accumulation
├── hype_monitor.py            ← WS price + REST staking
├── deployment_monitor.py      ← REST poll 60s
├── oi_monitor.py              ← REST poll 5min
└── whale_monitor.py           ← REST poll 60s
schedulers/
└── fees_scheduler.py          ← 24H fees digest tiap 1 jam
utils/
├── grouper.py                 ← Bundle alerts tiap 30 detik
├── formatter.py               ← Format pesan + HypurrScan links
└── storage.py                 ← Wallet watchlist persistence
```