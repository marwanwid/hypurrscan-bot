"""
db/database.py
Lightweight in-memory "database" untuk:
  - list_wallets()     → ambil wallet dari Storage
  - is_alert_sent()    → cek dedup alert
  - mark_alert_sent()  → tandai alert sudah terkirim
"""
import logging

log = logging.getLogger(__name__)

_storage = None
_sent_alerts: set = set()

MAX_DEDUP_SIZE = 100_000


def init_db(storage):
    global _storage
    _storage = storage
    log.info("db.database initialized with Storage")


async def list_wallets() -> list:
    if _storage is None:
        log.warning("list_wallets called before init_db()")
        return []
    wallets = _storage.get_wallets()
    return [
        {"address": addr, "label": meta.get("label", "")}
        for addr, meta in wallets.items()
    ]


async def is_alert_sent(key: str) -> bool:
    return key in _sent_alerts


async def mark_alert_sent(key: str):
    global _sent_alerts  # ← HARUS di atas sebelum variable dipakai
    _sent_alerts.add(key)
    if len(_sent_alerts) > MAX_DEDUP_SIZE:
        _sent_alerts = set(list(_sent_alerts)[MAX_DEDUP_SIZE // 2:])
        log.debug(f"dedup set trimmed to {len(_sent_alerts)} entries")
