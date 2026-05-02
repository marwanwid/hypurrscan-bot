async def _check_staking(self):
    """
    Track individual delegator stake changes per validator.
    Alert kalau ada address yang stake/unstake > HYPE_STAKE_THRESHOLD dalam satu poll.
    """
    import aiohttp
    from config import HL_API_URL

    HYPE_DECIMALS = 1_000_000  # HYPE uses 6 decimal places

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            # Step 1: ambil list semua validator
            async with session.post(HL_API_URL, json={"type": "validatorSummaries"}) as resp:
                if resp.status != 200:
                    return
                validators = await resp.json()
    except Exception as e:
        logger.debug(f"Staking fetch error: {e}")
        return

    if not isinstance(validators, list):
        return

    # Step 2: untuk setiap validator, ambil list delegator-nya
    current_snapshot = {}  # key: "userAddr_validatorAddr" -> HYPE amount (normalized)

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            for v in validators:
                validator_addr = v.get("validator") or v.get("address") or ""
                if not validator_addr:
                    continue

                try:
                    async with session.post(
                        HL_API_URL,
                        json={"type": "delegations", "validator": validator_addr}
                    ) as resp:
                        if resp.status != 200:
                            continue
                        delegations = await resp.json()
                except Exception:
                    continue

                if not isinstance(delegations, list):
                    continue

                for d in delegations:
                    user_addr = d.get("delegator") or d.get("user") or d.get("address") or ""
                    raw_amount = float(d.get("amount") or d.get("stake") or d.get("stakedAmount") or 0)
                    normalized = raw_amount / HYPE_DECIMALS  # convert to actual HYPE

                    if user_addr:
                        key = f"{user_addr}_{validator_addr}"
                        current_snapshot[key] = {
                            "user": user_addr,
                            "validator": validator_addr,
                            "amount": normalized,
                        }

                await asyncio.sleep(0.1)  # jangan spam API

    except Exception as e:
        logger.error(f"Delegations fetch error: {e}")
        return

    # Step 3: compare snapshot, detect perubahan individual
    if not self._last_stake_snapshot:
        self._last_stake_snapshot = current_snapshot
        logger.info(f"Staking baseline set: {len(current_snapshot)} delegator-validator pairs")
        return

    for key, data in current_snapshot.items():
        old_data = self._last_stake_snapshot.get(key)
        old_amount = old_data["amount"] if old_data else 0.0
        new_amount = data["amount"]
        delta = new_amount - old_amount

        if abs(delta) >= HYPE_STAKE_THRESHOLD:
            action = "stake" if delta > 0 else "unstake"
            msg = hype_staking_alert(action, abs(delta), data["user"])
            await self.grouper.add("HYPE Staking", msg)
            logger.info(
                f"Staking: {action} {abs(delta):,.0f} HYPE "
                f"by {data['user'][:10]}... on {data['validator'][:10]}..."
            )

    # Detect delegator yang keluar total (unstake semua)
    for key, old_data in self._last_stake_snapshot.items():
        if key not in current_snapshot and old_data["amount"] >= HYPE_STAKE_THRESHOLD:
            msg = hype_staking_alert("unstake", old_data["amount"], old_data["user"])
            await self.grouper.add("HYPE Staking", msg)
            logger.info(f"Full unstake: {old_data['amount']:,.0f} HYPE by {old_data['user'][:10]}...")

    self._last_stake_snapshot = current_snapshot