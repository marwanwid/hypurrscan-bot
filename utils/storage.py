"""
utils/storage.py — JSON-based persistent storage for wallet watchlist
"""

import json
import logging
import os
from typing import Dict, Optional

from config import WALLETS_FILE

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self):
        os.makedirs(os.path.dirname(WALLETS_FILE), exist_ok=True)
        self._data: Dict[str, dict] = self._load()

    def _load(self) -> dict:
        if os.path.exists(WALLETS_FILE):
            try:
                with open(WALLETS_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load wallets: {e}")
        return {"wallets": {}}

    def _save(self):
        try:
            with open(WALLETS_FILE, "w") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save wallets: {e}")

    def add_wallet(self, address: str, label: Optional[str] = None) -> bool:
        address = address.lower()
        if address in self._data["wallets"]:
            return False  # already exists
        self._data["wallets"][address] = {"label": label or address[:8] + "..."}
        self._save()
        return True

    def remove_wallet(self, address: str) -> bool:
        address = address.lower()
        if address not in self._data["wallets"]:
            return False
        del self._data["wallets"][address]
        self._save()
        return True

    def get_wallets(self) -> Dict[str, dict]:
        return self._data["wallets"]

    def get_label(self, address: str) -> str:
        address = address.lower()
        return self._data["wallets"].get(address, {}).get("label", address[:10] + "...")
