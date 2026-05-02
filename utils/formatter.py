"""
utils/formatter.py — Emoji-rich Telegram message formatting
"""

from datetime import datetime


def ts() -> str:
    return datetime.utcnow().strftime("%H:%M:%S UTC")


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


def liquidation_alert(address: str, account_value: float, positions: list, leverage_type: str) -> str:
    pos_lines = ""
    for p in positions[:5]:  # max 5 positions shown
        side = "Long 🟢" if float(p.get("szi", 0)) > 0 else "Short 🔴"
        pos_lines += f"\n  • {p.get('coin', '?')} {side} — {fmt_usd(abs(float(p.get('szi', 0))) * float(p.get('px', 0)))}"

    short_addr = f"{address[:6]}...{address[-4:]}"
    return (
        f"🚨 *LIQUIDATION ALERT*\n"
        f"Address: `{short_addr}`\n"
        f"Account Value: *{fmt_usd(account_value)}*\n"
        f"Type: {leverage_type}\n"
        f"Positions:{pos_lines}\n"
        f"🕐 {ts()}"
    )


def twap_alert(coin: str, side: str, notional: float, address: str, duration_min: int) -> str:
    side_emoji = "🟢 BUY" if side.upper() in ("B", "BUY", "LONG") else "🔴 SELL"
    short_addr = f"{address[:6]}...{address[-4:]}" if address else "Unknown"
    return (
        f"📊 *LARGE TWAP DETECTED*\n"
        f"Coin: *{coin}*\n"
        f"Side: {side_emoji}\n"
        f"Notional: *{fmt_usd(notional)}*\n"
        f"Duration: {duration_min} min\n"
        f"By: `{short_addr}`\n"
        f"🕐 {ts()}"
    )


def deployment_alert(token_name: str, token_address: str, deployer: str, token_type: str) -> str:
    short_deployer = f"{deployer[:6]}...{deployer[-4:]}" if deployer else "Unknown"
    emoji = "🪙" if token_type.lower() == "spot" else "📈"
    return (
        f"{emoji} *NEW {token_type.upper()} DEPLOYMENT*\n"
        f"Token: *{token_name}*\n"
        f"Address: `{token_address}`\n"
        f"Deployer: `{short_deployer}`\n"
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
    short_addr = f"{address[:6]}...{address[-4:]}" if address else "Unknown"
    return (
        f"🐋 *LARGE PERP POSITION*\n"
        f"Coin: *{coin}*\n"
        f"Side: {side_emoji}\n"
        f"Notional: *{fmt_usd(notional)}*\n"
        f"Price: ${price:,.2f}\n"
        f"By: `{short_addr}`\n"
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
    short_addr = f"{address[:6]}...{address[-4:]}" if address else "Unknown"
    return (
        f"{emoji} *HYPE STAKING MOVEMENT*\n"
        f"Action: *{action.upper()}*\n"
        f"Amount: *{fmt_num(amount)} HYPE*\n"
        f"By: `{short_addr}`\n"
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
    short_addr = f"{address[:6]}...{address[-4:]}"
    return (
        f"{emoji} *WHALE ALERT — {event_type.upper()}*\n"
        f"Label: *{label}*\n"
        f"Address: `{short_addr}`\n"
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
