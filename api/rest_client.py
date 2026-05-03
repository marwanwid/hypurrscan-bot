"""
api/rest_client.py
Async REST helpers untuk Hyperliquid API.
"""
import logging

import aiohttp

from config import HL_API_URL

log = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=15)


async def _post(payload: dict) -> dict:
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(HL_API_URL, json=payload) as resp:
                if resp.status == 200:
                    return await resp.json()
                log.warning(f"HL REST {payload.get('type')} → HTTP {resp.status}")
    except Exception as e:
        log.error(f"HL REST error [{payload.get('type')}]: {e}")
    return {}


async def get_clearinghouse_state(address: str) -> dict:
    """Fetch posisi + margin summary untuk satu address."""
    return await _post({"type": "clearinghouseState", "user": address})


async def get_meta() -> dict:
    """Fetch universe metadata (list semua perp coins)."""
    return await _post({"type": "meta"})
