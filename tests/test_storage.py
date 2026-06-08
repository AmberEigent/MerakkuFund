"""Tests for the Layer 1 SQLite data store + trades cache + graph persistence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polyagents.dataflows.news import NewsClient
from polyagents.dataflows.types import Candle
from polyagents.dataflows.volume import enrich_candles_with_volume
from polyagents.default_config import DEFAULT_CONFIG
from polyagents.graph.setup import build_data_collection_graph
from polyagents.graph.state import build_initial_state
from polyagents.storage.db import DataStore

from .conftest import FakeClient


# --- CRUD --------------------------------------------------------------------

def test_market_candles_orderbook_collection_roundtrip(tmp_path, sample_market):
    store = DataStore(tmp_path / "d.db")
    store.record_market(sample_market)
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    candles = [Candle(base + timedelta(hours=i), 0.5, 0.5, 0.5, 0.5, float(i)) for i in range(3)]
    store.upsert_candles("tok", candles)
    store.upsert_candles("tok", candles)              # idempotent (PK on ts)
    store.record_orderbook("tok", {"available": True, "mid": 0.5, "best_bid": 0.49})
    store.record_collection("tok", "2026-06-01T00:00:00+00:00", "Q?", 0.5, {"features": {}})

    c = store.counts()
    assert c["markets"] == 1 and c["candles"] == 3 and c["orderbook_snapshots"] == 1 and c["collections"] == 1
    got = store.get_candles("tok")
    assert len(got) == 3 and got[-1].volume == 2.0
    store.close()


def test_trades_dedupe_and_query(tmp_path):
    store = DataStore(tmp_path / "d.db")
    trades = [{"transactionHash": "h1", "asset": "A", "timestamp": 100, "size": 5, "price": 0.5, "side": "BUY"},
              {"transactionHash": "h2", "asset": "B", "timestamp": 200, "size": 9, "price": 0.4, "side": "SELL"}]
    store.insert_trades("C", trades)
    store.insert_trades("C", trades)                  # same keys -> ignored
    assert store.counts()["trades"] == 2
    assert [t["asset"] for t in store.fetch_trades("C", asset="A")] == ["A"]
    assert store.trade_ts_range("C") == (100, 200)
    store.close()


# --- trades cache (watermark) ------------------------------------------------

def test_trades_cache_avoids_refetch(tmp_path):
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    candles = [Candle(base + timedelta(hours=i), 0.5, 0.5, 0.5, 0.5, 0.0) for i in range(4)]
    lo = int(base.timestamp())
    trades = [{"transactionHash": "h1", "asset": "T", "timestamp": lo + 3600, "size": 10.0, "price": 0.5, "side": "BUY"}]

    class CountingClient:
        def __init__(self):
            self.calls = 0

        def fetch_market_trades(self, condition_id, min_ts=None, max_pages=25):
            self.calls += 1
            return list(trades)

    store = DataStore(tmp_path / "d.db")
    c = CountingClient()
    e1 = enrich_candles_with_volume(candles, "COND", "T", c, store=store)
    e2 = enrich_candles_with_volume(candles, "COND", "T", c, store=store)
    assert c.calls == 1                               # second run served from cache
    assert sum(x.volume for x in e1) == 10.0
    assert sum(x.volume for x in e2) == 10.0          # cache produces identical volume
    store.close()


# --- graph write-through -----------------------------------------------------

def test_collection_graph_persists(tmp_path, fake_client, sample_market):
    store = DataStore(tmp_path / "d.db")
    graph = build_data_collection_graph(
        fake_client, NewsClient(api_key=None), DEFAULT_CONFIG.copy(), store=store
    )
    graph.invoke(build_initial_state(sample_market, as_of="2026-06-08T00:00:00+00:00"))
    counts = store.counts()
    assert counts["candles"] > 0            # market_data collector wrote candles
    assert counts["orderbook_snapshots"] == 1
    assert counts["collections"] == 1       # features collector wrote the raw bundle
    assert counts["trades"] > 0             # volume cache persisted trades
    store.close()
