#!/usr/bin/env python3
"""
Daily Dollar Cost Averaging (DCA) Tracker
Simulates daily $10 purchases of 8 assets, tracks average cost and P&L,
and sends a daily report via Telegram Bot.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yfinance as yf

# ── Windows encoding workaround ────────────────────────────────────────────
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

# ── Configuration ──────────────────────────────────────────────────────────

DAILY_AMOUNT = 10.0  # $10 per asset per day

ASSETS = {
    "BTC":   {"type": "crypto", "ticker": "BTC-USD", "coin_id": "bitcoin",      "name": "Bitcoin"},
    "QQQ":   {"type": "stock",  "ticker": "QQQ",                                "name": "Invesco QQQ Trust"},
    "SPY":   {"type": "stock",  "ticker": "SPY",                                "name": "SPDR S&P 500 ETF"},
    "GOOGL": {"type": "stock",  "ticker": "GOOGL",                              "name": "Alphabet (Google)"},
    "HYPE":  {"type": "crypto", "ticker": "HYPE-USD", "coin_id": "hyperliquid",  "name": "Hyperliquid (DEX)"},
    "GLD":   {"type": "stock",  "ticker": "GLD",                                "name": "SPDR Gold Trust"},
    "BRK.B": {"type": "stock",  "ticker": "BRK-B",                              "name": "Berkshire Hathaway"},
    "MKL":   {"type": "stock",  "ticker": "MKL",                                "name": "Markel Insurance"},
}

# File to store all transaction history
DATA_FILE = Path(__file__).parent / "data" / "portfolio.json"

# ── Telegram config (from environment variables) ────────────────────────────

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")  # auto-discovered if empty
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else ""

# ── Price fetching ─────────────────────────────────────────────────────────

def fetch_crypto_price(coin_id: str) -> float | None:
    """Fetch crypto price from CoinGecko free API."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": coin_id, "vs_currencies": "usd"}
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return float(data[coin_id]["usd"])
    except Exception as e:
        print(f"  [ERROR] CoinGecko fetch failed for {coin_id}: {e}", file=sys.stderr)
        return None


def fetch_stock_price(ticker: str, retries: int = 3) -> float | None:
    """Fetch latest closing price via yfinance, with retry on rate limit."""
    for attempt in range(retries):
        try:
            t = yf.Ticker(ticker)
            price = t.fast_info.get("lastPrice") or t.fast_info.get("regularMarketPreviousClose")
            if price is None:
                hist = t.history(period="3d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
            if price is None:
                raise ValueError("No price data returned")
            return float(price)
        except Exception as e:
            msg = str(e)
            if "Rate limited" in msg or "Too Many Requests" in msg:
                wait = (attempt + 1) * 3
                print(f"  [RETRY] {ticker}: rate limited, waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
            elif attempt < retries - 1:
                time.sleep(1)
            else:
                print(f"  [ERROR] yfinance fetch failed for {ticker}: {e}", file=sys.stderr)
    return None


# Global price cache per run to avoid duplicate API calls
_price_cache: dict[str, float | None] = {}


def get_current_price(symbol: str, asset: dict) -> float | None:
    """Dispatch to the right fetcher based on asset type; caches result."""
    if symbol in _price_cache:
        return _price_cache[symbol]
    if asset["type"] == "crypto":
        price = fetch_crypto_price(asset["coin_id"])
    else:
        price = fetch_stock_price(asset["ticker"])
    _price_cache[symbol] = price
    return price

# ── Data persistence ───────────────────────────────────────────────────────

def load_portfolio() -> dict:
    """Load portfolio from JSON file, or return empty structure."""
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"purchases": []}


def save_portfolio(portfolio: dict) -> None:
    """Save portfolio to JSON file."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, indent=2, ensure_ascii=False, default=str)

# ── P&L calculation ────────────────────────────────────────────────────────

def calculate_stats(portfolio: dict) -> dict:
    """Calculate average cost, current value, and P&L for each asset."""
    purchases = portfolio.get("purchases", [])

    # Aggregate per asset
    assets_data: dict[str, dict] = {}
    for p in purchases:
        sym = p["symbol"]
        if sym not in assets_data:
            assets_data[sym] = {"total_cost": 0.0, "total_shares": 0.0, "purchases": 0}
        assets_data[sym]["total_cost"] += p["cost"]
        assets_data[sym]["total_shares"] += p["shares"]
        assets_data[sym]["purchases"] += 1

    # Compute stats
    stats = {}
    total_cost_all = 0.0
    total_value_all = 0.0

    for sym, info in ASSETS.items():
        ad = assets_data.get(sym, {"total_cost": 0.0, "total_shares": 0.0, "purchases": 0})
        avg_cost = ad["total_cost"] / ad["total_shares"] if ad["total_shares"] > 0 else 0.0

        current_price = get_current_price(sym, info)

        current_value = ad["total_shares"] * current_price if current_price else None
        pnl = (current_value - ad["total_cost"]) if current_value is not None else None
        pnl_pct = ((current_value - ad["total_cost"]) / ad["total_cost"] * 100) if (current_value is not None and ad["total_cost"] > 0) else None

        stats[sym] = {
            "name": info["name"],
            "avg_cost": round(avg_cost, 4),
            "current_price": round(current_price, 2) if current_price else None,
            "total_shares": round(ad["total_shares"], 8),
            "total_cost": round(ad["total_cost"], 2),
            "current_value": round(current_value, 2) if current_value is not None else None,
            "pnl": round(pnl, 2) if pnl is not None else None,
            "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            "num_purchases": ad["purchases"],
        }

        if ad["total_cost"] > 0:
            total_cost_all += ad["total_cost"]
        if current_value is not None and ad["total_cost"] > 0:
            total_value_all += current_value

    total_pnl = total_value_all - total_cost_all if total_cost_all > 0 else None
    total_pnl_pct = (total_pnl / total_cost_all * 100) if total_pnl is not None and total_cost_all > 0 else None

    return {
        "assets": stats,
        "summary": {
            "total_cost": round(total_cost_all, 2),
            "total_value": round(total_value_all, 2),
            "total_pnl": round(total_pnl, 2) if total_pnl is not None else None,
            "total_pnl_pct": round(total_pnl_pct, 2) if total_pnl_pct is not None else None,
            "total_purchases": len(purchases),
            "daily_investment": DAILY_AMOUNT * len(ASSETS),
        },
    }

# ── Buy action ─────────────────────────────────────────────────────────────

def execute_daily_purchase(portfolio: dict) -> dict:
    """Simulate buying $10 of each asset at today's price. Returns updated portfolio."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Check if we already bought today
    existing_dates = {p.get("date") for p in portfolio.get("purchases", [])}
    if today in existing_dates:
        print(f"[SKIP] Already purchased for {today}")
        return portfolio

    new_purchases = []
    for sym, info in ASSETS.items():
        price = get_current_price(sym, info)
        if price is None or price <= 0:
            print(f"  [SKIP] {sym}: could not fetch price, skipping today")
            continue

        shares = DAILY_AMOUNT / price
        purchase = {
            "date": today,
            "symbol": sym,
            "price": round(price, 4),
            "shares": round(shares, 8),
            "cost": DAILY_AMOUNT,
        }
        new_purchases.append(purchase)
        print(f"  [BUY]  ${DAILY_AMOUNT:.2f} {sym} @ ${price:.2f} -> {shares:.6f} shares")
        time.sleep(0.5)  # be gentle with APIs

    portfolio.setdefault("purchases", []).extend(new_purchases)
    return portfolio

# ── Telegram helpers ───────────────────────────────────────────────────────

def discover_chat_id() -> str | None:
    """Try to auto-discover chat_id from recent Telegram messages."""
    try:
        resp = requests.get(f"{TELEGRAM_API}/getUpdates", timeout=15)
        data = resp.json()
        if data.get("ok") and data.get("result"):
            # Return the chat_id from the most recent message
            for update in reversed(data["result"]):
                chat = update.get("message", {}).get("chat", {})
                cid = chat.get("id")
                if cid:
                    return str(cid)
    except Exception as e:
        print(f"  [WARN] Could not discover chat_id: {e}", file=sys.stderr)
    return None


def send_telegram(text: str) -> bool:
    """Send a message via Telegram Bot API. Returns True on success."""
    if not TELEGRAM_TOKEN:
        print("[WARN] TELEGRAM_TOKEN not set. Set it in GitHub Secrets or .env file.")
        print("-" * 64)
        print(text)
        print("-" * 64)
        return False

    chat_id = TELEGRAM_CHAT_ID or discover_chat_id()

    if not chat_id:
        print("[WARN] No Telegram chat_id found! Please send a message to @ninayulin_bot first.")
        print("-" * 64)
        print(text)
        print("-" * 64)
        return False

    try:
        # Split long messages (Telegram limit: 4096 chars)
        max_len = 4000
        parts = [text[i:i+max_len] for i in range(0, len(text), max_len)]

        for i, part in enumerate(parts):
            prefix = f"({i+1}/{len(parts)})\n" if len(parts) > 1 else ""
            resp = requests.post(
                f"{TELEGRAM_API}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": prefix + part,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
            data = resp.json()
            if not data.get("ok"):
                # Retry without HTML parse mode (fallback to plain text)
                resp2 = requests.post(
                    f"{TELEGRAM_API}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": prefix + part,
                        "disable_web_page_preview": True,
                    },
                    timeout=15,
                )
                if not resp2.json().get("ok"):
                    print(f"  [ERROR] Telegram send failed: {resp2.json()}", file=sys.stderr)
                    return False
            time.sleep(0.3)

        print(f"[OK] Report sent to Telegram chat {chat_id}")
        return True
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}", file=sys.stderr)
        return False

# ── Report generation ──────────────────────────────────────────────────────

def build_report(stats: dict) -> str:
    """Build a formatted Telegram HTML report."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append(f"<b>📊 Daily DCA Report</b>")
    lines.append(f"<i>{today}</i>")
    lines.append("")

    # Asset table header
    lines.append("<pre>")
    lines.append(f"{'Asset':<7} {'Shares':>10}  {'Avg$':>9}  {'Now$':>9}  {'P&L$':>9}  {'P&L%':>7}")
    lines.append("-" * 64)

    def fmt(v, width=10, decimals=2):
        if v is None:
            return "N/A".rjust(width)
        return f"{v:{width}.{decimals}f}"

    for sym, s in stats["assets"].items():
        if s["num_purchases"] == 0:
            continue
        lines.append(
            f"{sym:<7} {fmt(s['total_shares'], 10, 4)}  "
            f"{fmt(s['avg_cost'], 9, 2)}  {fmt(s['current_price'], 9, 2)}  "
            f"{fmt(s['pnl'], 9, 2)}  {fmt(s['pnl_pct'], 7, 2)}"
        )
    lines.append("</pre>")

    # Summary
    sm = stats["summary"]
    pnl_emoji = "🟢" if (sm["total_pnl"] or 0) >= 0 else "🔴"

    lines.append("")
    lines.append("<b>── Portfolio Summary ──</b>")
    lines.append(f"💰 Total Cost:   <b>${sm['total_cost']:,.2f}</b>")
    lines.append(f"📦 Total Value:  <b>${sm['total_value']:,.2f}</b>")
    if sm["total_pnl"] is not None:
        lines.append(f"{pnl_emoji} Total P&amp;L:   <b>${sm['total_pnl']:,.2f} ({sm['total_pnl_pct']:+.2f}%)</b>")
    lines.append(f"📅 Daily Invest: ${sm['daily_investment']:,.2f}")
    lines.append(f"📊 Total Trades: {sm['total_purchases']}")

    return "\n".join(lines)

# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("  Daily DCA Tracker")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 64)

    # 1. Load portfolio
    portfolio = load_portfolio()

    # 2. Execute today's purchases
    print("\n>>> Executing daily purchases ($10 each)...")
    portfolio = execute_daily_purchase(portfolio)

    # 3. Save
    save_portfolio(portfolio)
    print(f"\n💾 Portfolio saved ({len(portfolio.get('purchases', []))} total trades)")

    # 4. Calculate stats
    print("\n📈 Calculating performance...")
    stats = calculate_stats(portfolio)

    # 5. Build & send report via Telegram
    print("\n📨 Sending report to Telegram...")
    report = build_report(stats)
    send_telegram(report)

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
