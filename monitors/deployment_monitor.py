"""
monitors/deployment_monitor.py
Deteksi token spot dan perp HIP-3 baru via official HL API.
"""

from typing import Set

import aiohttp

from config import POLL_DEPLOYMENT_SEC, HL_API_URL
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

            asset_id = name

            if not self._initialized:
                self._seen_perp.add(asset_id)
                continue

            if asset_id not in self._seen_perp:
                self._seen_perp.add(asset_id)

                if ":" in name:
                    # HIP-3 market — coba fetch auction price
                    deployer = asset.get("deployer") or ""
                    auction_price = await self._get_auction_price(name)
                    extra = {"auction_price": auction_price} if auction_price else {}
                    msg = deployment_alert(name, "", deployer, "PERP HIP-3", extra)
                    await self.grouper.add("New Deployments", msg)
                    self.logger.info(f"New HIP-3 perp: {name}")
                else:
                    msg = deployment_alert(name, "", "", "PERP")
                    await self.grouper.add("New Deployments", msg)
                    self.logger.info(f"New official perp: {name}")

    async def _get_auction_price(self, ticker: str) -> str:
        """Coba ambil harga auction terakhir untuk HIP-3 ticker."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(
                    HL_API_URL,
                    json={"type": "perpDexAuctions"}
                ) as resp:
                    if resp.status != 200:
                        return ""
                    data = await resp.json()
                    if not isinstance(data, list):
                        return ""
                    for auction in data:
                        if auction.get("name") == ticker or auction.get("ticker") == ticker:
                            price = auction.get("auctionPrice") or auction.get("price") or ""
                            if price:
                                return f"{float(price):,.2f}"
        except Exception:
            pass
        return ""