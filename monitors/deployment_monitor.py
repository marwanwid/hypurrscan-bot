"""
monitors/deployment_monitor.py
Detects new spot and perp token deployments on Hyperliquid.
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

    async def _check_spot(self):
        """Check for new spot token deployments."""
        data = await self.hypurrscan_get("/deployments", params={"type": "spot", "limit": 30})
        if data is None:
            # Fallback: official HL spotMeta
            resp = await self.hl_post({"type": "spotMeta"})
            if resp:
                tokens = resp.get("tokens", [])
                for token in tokens:
                    token_id = str(token.get("index") or token.get("tokenId") or token.get("name", ""))
                    if not token_id:
                        continue
                    if not self._initialized:
                        self._seen_spot.add(token_id)
                        continue
                    if token_id not in self._seen_spot:
                        self._seen_spot.add(token_id)
                        name = token.get("name", "Unknown")
                        address = token.get("evmContract") or ""
                        msg = deployment_alert(name, address, "", "SPOT")
                        await self.grouper.add("New Deployments", msg)
                        self.logger.info(f"New SPOT token: {name}")
            return

        items = data if isinstance(data, list) else data.get("data", data.get("deployments", []))
        for item in items:
            token_id = str(item.get("id") or item.get("tokenId") or item.get("address") or item.get("txHash", ""))
            if not token_id:
                continue
            if not self._initialized:
                self._seen_spot.add(token_id)
                continue
            if token_id not in self._seen_spot:
                self._seen_spot.add(token_id)
                name = item.get("name") or item.get("tokenName") or "Unknown"
                address = item.get("address") or item.get("tokenAddress") or ""
                deployer = item.get("deployer") or item.get("user") or ""
                msg = deployment_alert(name, address, deployer, "SPOT")
                await self.grouper.add("New Deployments", msg)
                self.logger.info(f"New SPOT deployment: {name}")

    async def _check_perp(self):
        """Check for new perp deployments via HIP-3."""
        resp = await self.hl_post({"type": "perpDexs"})
        if not resp:
            return

        dexs = resp if isinstance(resp, list) else resp.get("perpDexs", [])
        for dex in dexs:
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
                self.logger.info(f"New PERP/HIP-3 deployment: {name}")

        if not self._initialized:
            self._initialized = True
            self.logger.info(f"Deployment baseline set: {len(self._seen_spot)} spot, {len(self._seen_perp)} perp")
