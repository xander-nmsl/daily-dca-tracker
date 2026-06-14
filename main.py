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

DAILY_AMOUNT = 10.0  # fallback $10 per asset per day

ASSETS = {
    # US / Crypto (daily_amount: 10.0 USD)
    "BTC":   {"type": "crypto", "ticker": "BTC-USD", "coin_id": "bitcoin",      "name": "Bitcoin",             "currency": "USD", "symbol_prefix": "$",   "daily_amount": 10.0},
    "QQQ":   {"type": "stock",  "ticker": "QQQ",                                "name": "Invesco QQQ Trust",    "currency": "USD", "symbol_prefix": "$",   "daily_amount": 10.0},
    "SPY":   {"type": "stock",  "ticker": "SPY",                                "name": "SPDR S&P 500 ETF",     "currency": "USD", "symbol_prefix": "$",   "daily_amount": 10.0},
    "GOOGL": {"type": "stock",  "ticker": "GOOGL",                              "name": "Alphabet (Google)",    "currency": "USD", "symbol_prefix": "$",   "daily_amount": 10.0},
    "HYPE":  {"type": "crypto", "ticker": "HYPE-USD", "coin_id": "hyperliquid",  "name": "Hyperliquid (DEX)",   "currency": "USD", "symbol_prefix": "$",   "daily_amount": 10.0},
    "GLD":   {"type": "stock",  "ticker": "GLD",                                "name": "SPDR Gold Trust",      "currency": "USD", "symbol_prefix": "$",   "daily_amount": 10.0},
    "BRK.B": {"type": "stock",  "ticker": "BRK-B",                              "name": "Berkshire Hathaway",   "currency": "USD", "symbol_prefix": "$",   "daily_amount": 10.0},
    "MKL":   {"type": "stock",  "ticker": "MKL",                                "name": "Markel Insurance",     "currency": "USD", "symbol_prefix": "$",   "daily_amount": 10.0},
    
    # A-Shares / Chinese Mutual Fund (daily_amount: 100.0 CNY)
    "沪深300ETF": {"type": "stock", "ticker": "510300.SS", "name": "沪深300ETF", "currency": "CNY", "symbol_prefix": "¥", "daily_amount": 100.0},
    "诺安多策略A": {"type": "fund",  "ticker": "320016",    "name": "诺安多策略混合A", "currency": "CNY", "symbol_prefix": "¥", "daily_amount": 100.0},
    "中国石化":  {"type": "stock", "ticker": "600028.SS", "name": "中国石化", "currency": "CNY", "symbol_prefix": "¥", "daily_amount": 100.0},
    "海澜之家":  {"type": "stock", "ticker": "600398.SS", "name": "海澜之家", "currency": "CNY", "symbol_prefix": "¥", "daily_amount": 100.0},
    "药明康德":  {"type": "stock", "ticker": "603259.SS", "name": "药明康德", "currency": "CNY", "symbol_prefix": "¥", "daily_amount": 100.0},
    "宁德时代":  {"type": "stock", "ticker": "300750.SZ", "name": "宁德时代", "currency": "CNY", "symbol_prefix": "¥", "daily_amount": 100.0},
    "上海莱士":  {"type": "stock", "ticker": "002252.SZ", "name": "上海莱士", "currency": "CNY", "symbol_prefix": "¥", "daily_amount": 100.0},
    "海尔智家":  {"type": "stock", "ticker": "600690.SS", "name": "海尔智家", "currency": "CNY", "symbol_prefix": "¥", "daily_amount": 100.0},
    "招商银行":  {"type": "stock", "ticker": "600036.SS", "name": "招商银行", "currency": "CNY", "symbol_prefix": "¥", "daily_amount": 100.0},

    # Hong Kong Shares (daily_amount: 100.0 HKD)
    "小米（港股）": {"type": "stock", "ticker": "1810.HK",   "name": "小米集团-W", "currency": "HKD", "symbol_prefix": "HK$", "daily_amount": 100.0},
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


def fetch_fund_price(fund_code: str) -> float | None:
    """Fetch Chinese mutual fund NAV (dwjz) from Eastmoney API."""
    import re
    try:
        url = f"https://fundgz.1234567.com.cn/js/{fund_code}.js"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        content = re.findall(r"jsonpgz\((.*)\);", resp.text)
        if content:
            data = json.loads(content[0])
            val = data.get("dwjz")
            if val:
                return float(val)
    except Exception as e:
        print(f"  [ERROR] Eastmoney fund fetch failed for {fund_code}: {e}", file=sys.stderr)
    return None


def get_current_price(symbol: str, asset: dict) -> float | None:
    """Dispatch to the right fetcher based on asset type; caches result."""
    if symbol in _price_cache:
        return _price_cache[symbol]
    if asset["type"] == "crypto":
        price = fetch_crypto_price(asset["coin_id"])
    elif asset["type"] == "fund":
        price = fetch_fund_price(asset["ticker"])
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
            "daily_investment": sum(a.get("daily_amount", DAILY_AMOUNT) for a in ASSETS.values()),
        },
    }


# ── Buy action ─────────────────────────────────────────────────────────────

def execute_daily_purchase(portfolio: dict) -> dict:
    """Simulate buying local currency amount of each asset at today's price. Returns updated portfolio."""
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

        daily_amount = info.get("daily_amount", DAILY_AMOUNT)
        shares = daily_amount / price
        purchase = {
            "date": today,
            "symbol": sym,
            "price": round(price, 4),
            "shares": round(shares, 8),
            "cost": daily_amount,
        }
        new_purchases.append(purchase)
        prefix = info.get("symbol_prefix", "$")
        print(f"  [BUY]  {prefix}{daily_amount:.2f} {sym} @ {prefix}{price:.2f} -> {shares:.6f} shares")
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

def get_visual_width(s: str) -> int:
    """Calculate visual width of a string (Chinese/full-width characters count as 2)."""
    return sum(2 if ord(c) > 127 else 1 for c in s)


def pad_string(s: str, width: int, align: str = "left") -> str:
    v_width = get_visual_width(s)
    padding = max(0, width - v_width)
    if align == "right":
        return " " * padding + s
    else:
        return s + " " * padding


def build_report(stats: dict) -> str:
    """Build a formatted Telegram HTML report showing only DCA days, average price, and P&L ratio."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append(f"<b>📊 Daily DCA Report</b>")
    lines.append(f"<i>{today}</i>")
    lines.append("")

    # Asset table header
    # Header fields: Asset (left 12), Days (right 4), AvgCost (right 11), P&L% (right 8)
    # Total visual width = 12 + 1 (space) + 4 + 2 (spaces) + 11 + 2 (spaces) + 8 = 40
    lines.append("<pre>")
    header = f"{pad_string('Asset', 12)} {pad_string('Days', 4, 'right')}  {pad_string('AvgCost', 11, 'right')}  {pad_string('P&L%', 8, 'right')}"
    lines.append(header)
    lines.append("-" * 40)

    for sym, s in stats["assets"].items():
        info = ASSETS.get(sym, {})
        prefix = info.get("symbol_prefix", "")
        avg_cost_val = s['avg_cost']
        avg_cost_str = f"{prefix}{avg_cost_val:.2f}" if avg_cost_val > 0 else "N/A"
        
        pnl_pct = s['pnl_pct']
        pnl_pct_str = f"{pnl_pct:+.2f}%" if pnl_pct is not None else "N/A"
        
        row = (
            f"{pad_string(sym, 12)} "
            f"{pad_string(str(s['num_purchases']), 4, 'right')}  "
            f"{pad_string(avg_cost_str, 11, 'right')}  "
            f"{pad_string(pnl_pct_str, 8, 'right')}"
        )
        lines.append(row)
    lines.append("</pre>")

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
