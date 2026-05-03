"""
api/ws_client.py
Shared WebSocket client untuk Hyperliquid.

Fitur:
  - register(channel, callback)  → daftarkan async handler
  - subscribe(sub_dict)          → kirim subscription (langsung atau queued)
  - run()                        → loop koneksi + dispatch
"""
import asyncio
import json
import logging
from collections import defaultdict

import websockets

from config import HL_WS_URL

log = logging.getLogger(__name__)


class HyperliquidWS:
    def __init__(self):
        # channel → list of async callbacks
        self._handlers: defaultdict = defaultdict(list)
        # subscription dicts yang akan dikirim saat connect/reconnect
        self._subscriptions: list[dict] = []
        # referensi ws aktif (untuk subscribe on-the-fly)
        self._ws = None
        self._lock = asyncio.Lock()

    def register(self, channel: str, callback):
        """Daftarkan async callback untuk channel tertentu (e.g. 'trades')."""
        self._handlers[channel].append(callback)
        log.debug(f"WS handler registered for channel='{channel}'")

    def subscribe(self, sub_dict: dict):
        """
        Tambahkan subscription.
        Kalau WS sudah konek, langsung kirim. Kalau belum, queue dulu.
        """
        self._subscriptions.append(sub_dict)
        # Fire-and-forget kalau ws sudah aktif
        if self._ws is not None:
            asyncio.create_task(self._send_sub(sub_dict))

    async def _send_sub(self, sub_dict: dict):
        try:
            if self._ws:
                await self._ws.send(json.dumps({
                    "method": "subscribe",
                    "subscription": sub_dict,
                }))
        except Exception as e:
            log.debug(f"WS send_sub error: {e}")

    async def run(self):
        """Main loop — reconnect otomatis."""
        log.info("HyperliquidWS starting")
        while True:
            try:
                await self._connect()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning(f"HyperliquidWS disconnected: {e} — reconnect in 10s")
                self._ws = None
                await asyncio.sleep(10)

    async def _connect(self):
        async with websockets.connect(
            HL_WS_URL,
            ping_interval=20,
            ping_timeout=10,
            open_timeout=30,
        ) as ws:
            self._ws = ws
            log.info(f"HyperliquidWS connected — sending {len(self._subscriptions)} subscriptions")

            # Kirim semua subscription yang sudah terdaftar
            for sub in self._subscriptions:
                await ws.send(json.dumps({"method": "subscribe", "subscription": sub}))
                await asyncio.sleep(0.03)  # hindari flood

            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    channel = msg.get("channel", "")
                    handlers = self._handlers.get(channel, [])
                    for handler in handlers:
                        # Jalankan handler sebagai task supaya tidak block loop
                        asyncio.create_task(handler(msg))
                except Exception as e:
                    log.debug(f"WS dispatch error: {e}")
