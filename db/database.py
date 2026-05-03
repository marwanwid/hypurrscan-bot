"""
db/database.py
Lightweight in-memory "database" untuk:
  - list_wallets()     → ambil wallet dari Storage
  - is_alert_sent()    → cek dedup alert
  - mark_alert_sent()  → tandai alert sudah terkirim

Tidak butuh SQLite / Redis — cukup in-memory karena:
  - Dedup window order_monitor sudah di-handle via alert_key per window period
  - Wallet list persistent via utils/storage.py (JSON file)
"""
import logging
from typing import Optional

log = logging.getLogger(__name__)

# ── State ─────────────────────────────────────────────────────────────────────

_storage = None           # diisi via init_db()
_sent_alerts: set = set() # in-memory dedup set

MAX_DEDUP_SIZE = 100_000  # batas set agar tidak bocor memori


def init_db(storage):
    """
    Panggil sekali dari main.py setelah Storage dibuat.
    Contoh: db.database.init_db(storage)
    """
    global _storage
    _storage = storage
    log.info("db.database initialized with Storage")


# ── Wallet helpers ─────────────────────────────────────────────────────────────

async def list_wallets() -> list[dict]:
    """
    Return list wallet dari Storage.
    Format: [{"address": "0x...", "label": "..."}, ...]
    """
    if _storage is None:
        log.warning("list_wallets called before init_db()")
        return []
    wallets = _storage.get_wallets()
    return [
        {"address": addr, "label": meta.get("label", "")}
        for addr, meta in wallets.items()
    ]


# ── Alert dedup ────────────────────────────────────────────────────────────────

async def is_alert_sent(key: str) -> bool:
    """True kalau alert_key sudah pernah dikirim."""
    return key in _sent_alerts


async def mark_alert_sent(key: str):
    """Tandai alert_key sudah terkirim."""
    _sent_alerts.add(key)
    # Cleanup kalau set terlalu besar
    if len(_sent_alerts) > MAX_DEDUP_SIZE:
        # Hapus separuh entri terlama (convert ke list, ambil setengah terakhir)
        global _sent_alerts
        trimmed = set(list(_sent_alerts)[MAX_DEDUP_SIZE // 2:])
        _sent_alerts = trimmed
        log.debug(f"dedup set trimmed to {len(_sent_alerts)} entries")
