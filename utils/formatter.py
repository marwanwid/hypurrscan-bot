"""
utils/formatter.py — Emoji-rich Telegram message formatting
"""

from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
HL_SCAN = "https://hypurrscan.io/address"


def ts() -> str:
    return datetime.now(WIB).strftime("%H:%M:%S WIB")


def fmt_usd(value: float) -> str:
    if value >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value/1_000:.1f}K"
    return f"${value:.2f}"


def fmt_num(value: float, decimals: int = 2) -> str:
    if value >= 1_000_000:
        return f"{value/1_000_000:.{decimals}f}M"
    if value >= 1_000:
        return f"{value/1_000:.{decimals}f}K"
    return f"{value:.{decimals}f}"


def addr_link(address: str) -> str:
    """Return a Telegram markdown link for an address."""
    if not address or address == "Unknown":
        return "Unknown"
    short = f"{address[:6]}...{address[-4:]}"
    return f"[{short}]({HL_SCAN}/{address})"


def liquidation_alert(address: str, account_value: float, positions: list, leverage_type: str) -> str:
    # Kalau leverage_type berisi info coin & side (dari liquidation baru)
    # format lebih simple
    pos_lines = ""
    for p in positions[:5]:
        side_str = "Long 🔴" if float(p.get("szi", 0)) > 0 else "Short 🟢"
        val = abs(float(p.get("szi", 0))) * float(p.get("px", 0))
        if val > 0:
            pos_lines += f"\n  • {p.get('coin', '?')} {side_str} — {fmt_usd(val)}"

    return (
        f"🚨 *LIQUIDATION ALERT*\n"
        f"Address: {addr_link(address)}\n"
        f"Value: *{fmt_usd(account_value)}*\n"
        f"Detail: {leverage_type}\n"
        f"{pos_lines}\n"
        f"🕐 {ts()}"
    )


def twap_alert(coin: str, side: str, notional: float, address: str, duration_min: int) -> str:
    side_emoji = "🟢 BUY" if side.upper() in ("B", "BUY", "LONG") else "🔴 SELL"
    return (
        f"📊 *LARGE TWAP DETECTED*\n"
        f"Coin: *{coin}*\n"
        f"Side: {side_emoji}\n"
        f"Notional: *{fmt_usd(notional)}*\n"
        f"Duration: {duration_min} min\n"
        f"By: {addr_link(address)}\n"
        f"🕐 {ts()}"
    )


def deployment_alert(token_name: str, token_address: str, deployer: str, token_type: str, extra: dict = None) -> str:
    extra = extra or {}

    if "HIP-3" in token_type.upper() or "PERP HIP" in token_type.upper():
        # Parse namespace dan ticker dari nama seperti xyz:IHSG
        if ":" in token_name:
            namespace, ticker = token_name.split(":", 1)
        else:
            namespace, ticker = "hl", token_name

        deployer_line = f"Deployer: {addr_link(deployer)}\n" if deployer else ""
        auction_line = f"Auction Price: *{extra.get('auction_price', '')} HYPE*\n" if extra.get('auction_price') else ""

        return (
            f"📈 *NEW HIP-3 PERP DEPLOYMENT*\n"
            f"Ticker: *{token_name}*\n"
            f"Namespace: `{namespace}`\n"
            f"Market: *{ticker}-USDC*\n"
            f"{deployer_line}"
            f"{auction_line}"
            f"🔗 [Lihat di Hyperliquid](https://app.hyperliquid.xyz/trade/{ticker})\n"
            f"🕐 {ts()}"
        )

    elif token_type.upper() == "PERP":
        return (
            f"📈 *NEW PERP LISTING*\n"
            f"Ticker: *{token_name}*\n"
            f"Market: *{token_name}-USDC*\n"
            f"🔗 [Lihat di Hyperliquid](https://app.hyperliquid.xyz/trade/{token_name})\n"
            f"🕐 {ts()}"
        )

    else:
        # SPOT
        deployer_line = f"Deployer: {addr_link(deployer)}\n" if deployer else ""
        address_line = f"Address: {addr_link(token_address)}\n" if token_address else ""
        return (
            f"🪙 *NEW SPOT DEPLOYMENT*\n"
            f"Token: *{token_name}*\n"
            f"{address_line}"
            f"{deployer_line}"
            f"🔗 [Lihat di Hyperliquid](https://app.hyperliquid.xyz/spot/{token_name})\n"
            f"🕐 {ts()}"
        )


def oi_spike_alert(coin: str, old_oi: float, new_oi: float, pct: float) -> str:
    direction = "⬆️" if new_oi > old_oi else "⬇️"
    return (
        f"📉 *OI SPIKE ALERT*\n"
        f"Coin: *{coin}*\n"
        f"Change: {direction} *{pct:+.1f}%*\n"
        f"OI: {fmt_usd(old_oi)} → *{fmt_usd(new_oi)}*\n"
        f"🕐 {ts()}"
    )


def large_perp_trade_alert(coin: str, side: str, notional: float, price: float, address: str) -> str:
    side_emoji = "🟢 LONG" if side.upper() in ("B", "BUY", "LONG") else "🔴 SHORT"
    return (
        f"🐋 *LARGE PERP POSITION*\n"
        f"Coin: *{coin}*\n"
        f"Side: {side_emoji}\n"
        f"Notional: *{fmt_usd(notional)}*\n"
        f"Price: ${price:,.2f}\n"
        f"By: {addr_link(address)}\n"
        f"🕐 {ts()}"
    )


def large_spot_trade_alert(coin: str, side: str, notional: float, price: float) -> str:
    side_emoji = "🟢 BUY" if side.upper() in ("B", "BUY") else "🔴 SELL"
    return (
        f"💰 *LARGE SPOT TRADE*\n"
        f"Token: *{coin}*\n"
        f"Side: {side_emoji}\n"
        f"Notional: *{fmt_usd(notional)}*\n"
        f"Price: ${price:,.4f}\n"
        f"🕐 {ts()}"
    )


def hype_price_level_alert(price: float, level: float) -> str:
    direction = "⬆️" if price >= level else "⬇️"
    return (
        f"💜 *HYPE PRICE MILESTONE*\n"
        f"{direction} HYPE hit *${level:.0f}*\n"
        f"Current: *${price:.2f}*\n"
        f"🕐 {ts()}"
    )


def hype_spike_alert(price_now: float, price_before: float, pct: float, window_min: int) -> str:
    direction = "🚀 PUMP" if pct > 0 else "💥 DUMP"
    return (
        f"⚡ *HYPE UNUSUAL MOVE — {direction}*\n"
        f"Change: *{pct:+.2f}%* in {window_min} min\n"
        f"${price_before:.2f} → *${price_now:.2f}*\n"
        f"🕐 {ts()}"
    )


def hype_staking_alert(action: str, amount: float, address: str) -> str:
    emoji = "🔒" if action == "stake" else "🔓"
    return (
        f"{emoji} *HYPE STAKING MOVEMENT*\n"
        f"Action: *{action.upper()}*\n"
        f"Amount: *{fmt_num(amount)} HYPE*\n"
        f"By: {addr_link(address)}\n"
        f"🕐 {ts()}"
    )


def whale_alert(address: str, label: str, event_type: str, amount: float, details: str = "") -> str:
    emoji_map = {
        "deposit": "📥",
        "withdraw": "📤",
        "liquidation": "💀",
        "large_trade": "🐳",
    }
    emoji = emoji_map.get(event_type, "🔔")
    return (
        f"{emoji} *WHALE ALERT — {event_type.upper()}*\n"
        f"Label: *{label}*\n"
        f"Address: {addr_link(address)}\n"
        f"Amount: *{fmt_usd(amount)}*\n"
        f"{details}\n"
        f"🕐 {ts()}"
    )


def fees_digest(total_fees_24h: float, period: str = "24H") -> str:
    return (
        f"📊 *{period} FEES DIGEST*\n"
        f"Protocol Fees: *{fmt_usd(total_fees_24h)}*\n"
        f"(Fees are used for HYPE buybacks)\n"
        f"🕐 {ts()}"
    )


def twap_digest(twaps: list) -> str:
    if not twaps:
        return f"📋 *ACTIVE TWAP DIGEST*\nNo large active TWAPs (>{fmt_usd(500_000)}) right now.\n🕐 {ts()}"

    lines = [f"📋 *ACTIVE TWAP DIGEST* — {len(twaps)} large orders\n"]
    for i, t in enumerate(twaps[:10], 1):
        side_e = "🟢" if t.get("side", "").upper() in ("B", "BUY") else "🔴"
        lines.append(
            f"{i}. {side_e} *{t.get('coin', '?')}* — {fmt_usd(t.get('notional', 0))} "
            f"({t.get('filled_pct', 0):.0f}% filled)"
        )
    lines.append(f"\n🕐 {ts()}")
    return "\n".join(lines)