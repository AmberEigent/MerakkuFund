"""Cross-market crypto MCP — public exchange REST (no key).

Polymarket crypto markets ("Will BTC be above $X?") track the underlying spot
closely, so the live crypto price is a strong cross-market signal — the Merakku
doc's cross-market-state-fusion idea and the DevBox example "does the exchange
price lead Polymarket?". An agent compares this with ``market_snapshot`` to spot
lag / mispricing.

Source: **Coinbase** public API (globally accessible, no key; Binance is
geo-blocked in some regions). Symbols are normalised, e.g. ``BTC`` / ``BTCUSDT``
→ the ``BTC-USD`` product. Errors return an error dict — the agent should say so,
not fabricate a price.
"""
from __future__ import annotations

import sys
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("crypto")
_SPOT = "https://api.coinbase.com"
_EXCH = "https://api.exchange.coinbase.com"
_http = httpx.Client(timeout=15.0, headers={"User-Agent": "polyagents/1.0"})

_GRAN = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "1d": 86400}


def _product(symbol: str) -> str:
    s = symbol.upper().replace("-", "").replace("/", "")
    for quote in ("USDT", "USDC", "USD"):
        if s.endswith(quote):
            s = s[: -len(quote)]
            break
    return f"{s}-USD"


@mcp.tool()
def crypto_price(symbol: str = "BTC") -> dict:
    """Live spot price for a crypto asset (e.g. BTC, ETH, SOL, or BTCUSDT)."""
    product = _product(symbol)
    try:
        d = _http.get(f"{_SPOT}/v2/prices/{product}/spot")
        d.raise_for_status()
        amt = d.json()["data"]["amount"]
        return {"symbol": product, "price": float(amt)}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "symbol": product}


@mcp.tool()
def crypto_24h(symbol: str = "BTC") -> dict:
    """24h stats: last price, % change from 24h open, high/low, volume."""
    product = _product(symbol)
    try:
        d = _http.get(f"{_EXCH}/products/{product}/stats")
        d.raise_for_status()
        j = d.json()
        op, last = float(j["open"]), float(j["last"])
        return {"symbol": product, "price": last,
                "change_pct": (last - op) / op if op else 0.0,
                "high": float(j["high"]), "low": float(j["low"]), "volume": float(j["volume"])}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "symbol": product}


@mcp.tool()
def crypto_klines(symbol: str = "BTC", interval: str = "1h", limit: int = 24) -> dict:
    """Recent OHLCV candles (interval 1m/5m/15m/1h/6h/1d). Returns the close series
    + summary so an agent can read momentum/volatility."""
    product = _product(symbol)
    gran = _GRAN.get(interval, 3600)
    try:
        d = _http.get(f"{_EXCH}/products/{product}/candles", params={"granularity": gran})
        d.raise_for_status()
        rows = d.json() or []                         # [time, low, high, open, close, volume], newest first
        closes = [float(r[4]) for r in rows][:limit][::-1]
        if not closes:
            return {"error": "no candles", "symbol": product}
        return {"symbol": product, "interval": interval, "n": len(closes),
                "last": closes[-1], "first": closes[0],
                "pct_change": (closes[-1] - closes[0]) / closes[0] if closes[0] else 0.0,
                "high": max(closes), "low": min(closes), "closes": closes}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "symbol": product}


def main() -> None:
    mcp.run(transport="streamable-http" if "--http" in sys.argv else "stdio")


if __name__ == "__main__":
    main()
