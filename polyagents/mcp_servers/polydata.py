"""Polymarket data MCP — events / price history / recent trades (REST, no key).

The Merakku doc lists poly_data (market/event/historical-trade retrieval). Its
implementation reads on-chain; we provide the same *capability* over Polymarket's
public REST (Gamma events + prices-history + data-api /trades), reusing
polyagents' data client — no wallet, no RPC, no key. (On-chain reads are a future
upgrade.)
"""
from __future__ import annotations

import sys
from datetime import timedelta

from mcp.server.fastmcp import FastMCP

from polyagents.dataflows.polymarket_client import PolymarketDataClient
from polyagents.dataflows.utils import utcnow
from polyagents.default_config import DEFAULT_CONFIG

mcp = FastMCP("polydata")
_client = PolymarketDataClient.from_config(DEFAULT_CONFIG)


@mcp.tool()
def list_events(limit: int = 20) -> list:
    """Active Polymarket EVENTS (markets grouped by event, e.g. a tournament or
    election), ordered by 24h volume. Use to find a theme, then drill into markets."""
    try:
        r = _client._http.get(
            f"{_client.gamma_base}/events",
            params={"active": "true", "closed": "false", "archived": "false",
                    "order": "volume24hr", "ascending": "false", "limit": limit},
        )
        r.raise_for_status()
        events = r.json() or []
    except Exception as exc:
        return [{"error": f"{type(exc).__name__}: {exc}"}]
    out = []
    for e in events[:limit]:
        markets = e.get("markets") or []
        out.append({
            "title": e.get("title", ""),
            "slug": e.get("slug", ""),
            "volume_24h": float(e.get("volume24hr") or 0.0),
            "liquidity": float(e.get("liquidity") or 0.0),
            "n_markets": len(markets),
            "ends": e.get("endDate"),
        })
    return out


@mcp.tool()
def recent_trades(condition_id: str, lookback_hours: int = 24) -> dict:
    """Aggregated recent /trades for a market: buy vs sell notional + count."""
    min_ts = int((utcnow() - timedelta(hours=lookback_hours)).timestamp())
    raw = _client.fetch_market_trades(condition_id, min_ts=min_ts)
    buy = sell = 0.0
    nb = ns = 0
    for t in raw:
        try:
            notional = float(t.get("size")) * float(t.get("price"))
        except (TypeError, ValueError):
            continue
        if str(t.get("side") or "").upper() == "SELL":
            sell += notional; ns += 1
        else:
            buy += notional; nb += 1
    total = buy + sell
    return {"condition_id": condition_id, "lookback_hours": lookback_hours,
            "n_trades": nb + ns, "buy_notional": round(buy, 2), "sell_notional": round(sell, 2),
            "flow_imbalance": round((buy - sell) / total, 4) if total else 0.0}


@mcp.tool()
def price_history(token_id: str, interval: str = "1w", fidelity: int = 60) -> dict:
    """Historical price series for a market side (interval: 1h/6h/1d/1w/max)."""
    candles = _client.fetch_price_history(token_id, interval=interval, fidelity=fidelity)
    if not candles:
        return {"token_id": token_id, "n": 0}
    closes = [c.close for c in candles]
    return {"token_id": token_id, "n": len(closes), "first": closes[0], "last": closes[-1],
            "high": max(closes), "low": min(closes),
            "pct_change": (closes[-1] - closes[0]) / closes[0] if closes[0] else 0.0,
            "start": candles[0].ts.isoformat(), "end": candles[-1].ts.isoformat()}


def main() -> None:
    mcp.run(transport="streamable-http" if "--http" in sys.argv else "stdio")


if __name__ == "__main__":
    main()
