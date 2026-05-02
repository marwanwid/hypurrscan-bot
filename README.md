# 🤖 Hyperliquid Monitor Bot

Telegram bot yang memonitor Hyperliquid 24/7 dan mengirimkan notifikasi real-time.

## 📋 Features

| Feature | Trigger |
|---------|---------|
| 💀 Liquidation Alert | Liquidasi address > $1M |
| 📊 TWAP Alert | TWAP baru > $1M notional |
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
git clone <your-repo>
cd hyperliquid-bot

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

### Option A: Via GitHub (Recommended)
1. Push code ke GitHub repo baru
2. Buka [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Pilih repo lu
4. Pergi ke **Variables** tab, tambahkan:
   - `TELEGRAM_BOT_TOKEN` = token dari BotFather
   - `TELEGRAM_CHAT_ID` = chat ID group lu
5. Railway auto-deploy! ✅

### Option B: Via Railway CLI
```bash
npm install -g @railway/cli
railway login
railway init
railway up
railway variables set TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=xxx
```

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

Edit `.env` atau set sebagai Railway environment variable:

```env
LIQUIDATION_THRESHOLD_USD=1000000    # Alert liquidasi >$1M
PERP_POSITION_THRESHOLD_USD=10000000 # Alert perp trade >$10M  
SPOT_TRADE_THRESHOLD_USD=1000000     # Alert spot trade >$1M
HYPE_PRICE_STEP=5                    # Alert tiap $5 milestone
HYPE_SPIKE_PERCENT=5                 # Alert kalau HYPE spike >5%
HYPE_SPIKE_WINDOW_MINUTES=15         # Window untuk spike detection
HYPE_STAKE_THRESHOLD=100000          # Alert stake/unstake >100K HYPE
```

## 🏗️ Architecture

```
main.py                  ← Entry point (PTB Application)
config.py                ← All settings from .env
├── bot/
│   └── commands.py      ← Telegram commands
├── monitors/
│   ├── liquidation_monitor.py   ← HypurrScan API poll (30s)
│   ├── twap_monitor.py          ← HypurrScan API poll (60s)
│   ├── deployment_monitor.py    ← HL API poll (60s)
│   ├── oi_monitor.py            ← HL API poll (5min)
│   ├── trade_monitor.py         ← WebSocket real-time
│   ├── hype_monitor.py          ← WebSocket + 60s poll
│   └── whale_monitor.py         ← HL API poll (60s)
├── schedulers/
│   ├── fees_scheduler.py        ← Every 6 hours
│   └── twap_digest_scheduler.py ← Every 6 hours
└── utils/
    ├── grouper.py       ← Alert bundler (30s window)
    ├── formatter.py     ← Message formatting
    └── storage.py       ← Wallet watchlist persistence
```

## 📝 Notes

- **HypurrScan API**: Bot uses `api.hypurrscan.io`. Jika ada endpoint yang berubah, adjust di `monitors/` files
- **Alert Grouping**: Alerts dibundle tiap 30 detik. Banyak event dalam 30 detik → 1 notif
- **Data persistence**: Wallet watchlist disimpan di `data/wallets.json` (Railway persistent volume atau local)
- **Railway Free Tier**: Cukup untuk bot ini karena hanya butuh 1 dyno/worker

## 🐛 Troubleshooting

**Bot tidak send notif:**
- Cek `TELEGRAM_CHAT_ID` sudah benar (pastikan bot sudah di-add ke group sebagai admin)
- Cek logs Railway untuk error

**HypurrScan API error:**
- API mungkin berubah endpoint — cek `api.hypurrscan.io/ui/` untuk docs terbaru
- Bot akan fallback ke Hyperliquid official API

**WebSocket disconnect:**
- Bot auto-reconnect tiap 10-15 detik kalau WebSocket putus
