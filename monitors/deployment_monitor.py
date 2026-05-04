"""
monitors/deployment_monitor.py
Deteksi token spot dan perp HIP-3 baru via official HL API.
HIP-3 perp muncul di metaAndAssetCtxs universe dengan prefix xyz:, cash:, vntl:, dll
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
        await self._check_perp_hip3()
        if not self._initialized:
            self._initialized = True
            self.logger.info(
                f"Deployment baseline: {len(self._seen_spot)} spot, "
                f"{len(self._seen_perp)} perp/HIP-3"
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

    async def _check_perp_hip3(self):
        """
        HIP-3 perp markets muncul di universe metaAndAssetCtxs.
        Mereka punya nama dengan prefix seperti xyz:ZM, cash:CAR, vntl:SOY, dll.
        Semua yang bukan nama plain (ada titik/colon) = HIP-3 market.
        """
        resp = await self.hl_post({"type": "metaAndAssetCtxs"})
        if not resp or not isinstance(resp, list) or len(resp) < 1:
            return

        universe = resp[0].get("universe", [])

        for asset in universe:
            if not isinstance(asset, dict):
                continue

            name = asset.get("name", "")
            if not name:
                continue

            # Semua perp di universe — track semuanya untuk detect baru
            asset_id = name  # name sudah unik

            if not self._initialized:
                self._seen_perp.add(asset_id)
                continue

            if asset_id not in self._seen_perp:
                self._seen_perp.add(asset_id)

                # Tentukan apakah HIP-3 (ada prefix dengan colon) atau perp biasa
                if ":" in name:
                    # HIP-3 market: xyz:ZM, cash:CAR, vntl:SOY, dll
                    deployer = asset.get("deployer") or ""
                    msg = deployment_alert(name, "", deployer, "PERP HIP-3")
                    await self.grouper.add("New Deployments", msg)
                    self.logger.info(f"New HIP-3 perp: {name}")
                else:
                    # Perp baru yang ditambah Hyperliquid official
                    msg = deployment_alert(name, "", "", "PERP")
                    await self.grouper.add("New Deployments", msg)
                    self.logger.info(f"New official perp: {name}")