"""
monitors/deployment_monitor.py
Deteksi token spot dan perp (HIP-3) baru via official HL API.
"""

from typing import Set

from config import POLL_DEPLOYMENT_SEC
from monitors.base import BaseMonitor
from utils.formatter import deployment_alert
from utils.grouper import AlertGrouper


class DeploymentMonitor(BaseMonitor):
    def __init__(self, grouper: AlertGrouper):
        super().__init__(grouper, poll_interval=POLL_DEPLOYMENT_SEC)
        self._seen_spot: Set[str] = set()
        self._seen_perp: Set[str] = set()
        self._initialized = False

    async def tick(self):
        await self._check_spot()
        await self._check_perp()
        if not self._initialized:
            self._initialized = True
            self.logger.info(
                f"Deployment baseline: {len(self._seen_spot)} spot, "
                f"{len(self._seen_perp)} perp"
            )

    async def _check_spot(self):
        resp = await self.hl_post({"type": "spotMeta"})
        if not resp or not isinstance(resp, dict):
            return

        for token in resp.get("tokens", []):
            if not isinstance(token, dict):
                continue
            token_id = str(token.get("index") or token.get("name") or "")
            if not token_id:
                continue
            if not self._initialized:
                self._seen_spot.add(token_id)
                continue
            if token_id not in self._seen_spot:
                self._seen_spot.add(token_id)
                name = token.get("name", "Unknown")
                address = token.get("evmContract") or token.get("tokenId") or ""
                msg = deployment_alert(name, str(address), "", "SPOT")
                await self.grouper.add("New Deployments", msg)
                self.logger.info(f"New SPOT token: {name}")

    async def _check_perp(self):
        resp = await self.hl_post({"type": "perpDexs"})
        # Fix: handle None response gracefully
        if not resp:
            return

        dexs = resp if isinstance(resp, list) else resp.get("perpDexs", []) if isinstance(resp, dict) else []

        for dex in dexs:
            if not isinstance(dex, dict):
                continue
            dex_id = str(dex.get("dexId") or dex.get("name") or "")
            if not dex_id:
                continue
            if not self._initialized:
                self._seen_perp.add(dex_id)
                continue
            if dex_id not in self._seen_perp:
                self._seen_perp.add(dex_id)
                name = dex.get("name") or dex_id
                deployer = dex.get("deployer") or ""
                msg = deployment_alert(name, dex_id, deployer, "PERP (HIP-3)")
                await self.grouper.add("New Deployments", msg)
                self.logger.info(f"New PERP deployment: {name}")