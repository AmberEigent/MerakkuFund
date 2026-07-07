"""Layer-1 data store — market/candle/trade/orderbook/collection cache.

Backed by SQLAlchemy Core so the same code runs on SQLite (dev/tests) and the
shared cloud PostgreSQL (prod). With ``POLYAGENTS_DATABASE_URL`` set every
instance reads/writes the same tables, so live fetches written through here
accumulate into one growing cloud cache — repeated runs stop re-hitting the API
and history builds up for backtesting/ML. With nothing set it falls back to a
local SQLite file (the classic dev behaviour), same code, two backends.

Persists what the collectors fetch:
  * ``markets``             — market metadata snapshots (one row per fetch)
  * ``candles``             — price-history bars per token (upsert by ts)
  * ``trades``              — raw trades per condition (deduped); powers the
                              volume-reconstruction cache and is the big API saver
  * ``orderbook_snapshots`` — L2 microstructure over time
  * ``collections``         — the full ``raw`` factor bundle per collect() run

Table names come from the ``aihf_`` registry in :mod:`polyagents.storage.tables`.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as _pg_insert
from sqlalchemy.dialects.sqlite import insert as _sqlite_insert

from polyagents.dataflows.types import Candle, Market

from .engine import coerce_url, get_engine, make_engine
from .tables import (l1_candles, l1_collections, l1_markets, l1_orderbook,
                     l1_trade_coverage, l1_trades, metadata)

_L1_TABLES = [l1_markets, l1_candles, l1_trades, l1_trade_coverage, l1_orderbook, l1_collections]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trade_key(t: dict) -> str:
    base = t.get("transactionHash") or t.get("id") or ""
    raw = f"{base}|{t.get('asset')}|{t.get('timestamp')}|{t.get('size')}|{t.get('price')}|{t.get('side')}"
    return hashlib.sha1(raw.encode()).hexdigest()


class DataStore:
    def __init__(self, url_or_path: str | None = None, *, engine=None) -> None:
        # engine → use it; None → the shared app engine (prod Postgres / dev
        # SQLite via POLYAGENTS_DATABASE_URL); an explicit path/url → that
        # SQLite file, UNLESS the shared cloud DB env is configured, in which
        # case every store shares the one cloud engine (so the cache is shared).
        if engine is not None:
            self.engine = engine
        elif url_or_path is None:
            self.engine = get_engine()
        elif os.getenv("POLYAGENTS_DATABASE_URL") or os.getenv("DATABASE_URL"):
            self.engine = get_engine()
        else:
            self.engine = make_engine(coerce_url(str(url_or_path)))
        metadata.create_all(self.engine, tables=_L1_TABLES)

    def close(self) -> None:
        self.engine.dispose()

    # ----- portable upsert ---------------------------------------------------

    def _upsert(self, table, rows: list[dict], *, index: list[str],
                update: list[str] | None = None) -> int:
        """Dialect-aware INSERT … ON CONFLICT. ``update`` set → replace those
        columns on conflict; omitted → do nothing (ignore duplicates)."""
        if not rows:
            return 0
        ins = _pg_insert if self.engine.dialect.name == "postgresql" else _sqlite_insert
        stmt = ins(table).values(rows)
        if update is None:
            stmt = stmt.on_conflict_do_nothing(index_elements=index)
        else:
            stmt = stmt.on_conflict_do_update(
                index_elements=index,
                set_={c: getattr(stmt.excluded, c) for c in update})
        with self.engine.begin() as cx:
            cx.execute(stmt)
        return len(rows)

    # ----- markets -----------------------------------------------------------

    def record_market(self, m: Market, fetched_at: str | None = None) -> None:
        self._upsert(l1_markets, [{
            "token_id": m.token_id, "condition_id": m.condition_id, "market_id": m.market_id,
            "question": m.question, "outcome": m.outcome, "price": m.price,
            "volume_24h": m.volume_24h, "liquidity": m.liquidity, "spread": m.spread,
            "days_to_expiry": m.days_to_expiry,
            "expiry": m.expiry.isoformat() if m.expiry else None,
            "fetched_at": fetched_at or _now(),
        }], index=["token_id", "fetched_at"],
            update=["condition_id", "market_id", "question", "outcome", "price",
                    "volume_24h", "liquidity", "spread", "days_to_expiry", "expiry"])

    # ----- candles -----------------------------------------------------------

    def upsert_candles(self, token_id: str, candles: Iterable[Candle]) -> int:
        fetched = _now()
        rows = [{
            "token_id": token_id, "ts": int(c.ts.timestamp()),
            "open": c.open, "high": c.high, "low": c.low, "close": c.close,
            "volume": c.volume, "fetched_at": fetched,
        } for c in candles]
        return self._upsert(l1_candles, rows, index=["token_id", "ts"],
                            update=["open", "high", "low", "close", "volume", "fetched_at"])

    def get_candles(self, token_id: str) -> list[Candle]:
        q = (select(l1_candles.c.ts, l1_candles.c.open, l1_candles.c.high, l1_candles.c.low,
                    l1_candles.c.close, l1_candles.c.volume)
             .where(l1_candles.c.token_id == token_id).order_by(l1_candles.c.ts))
        with self.engine.connect() as cx:
            rows = cx.execute(q).fetchall()
        return [Candle(datetime.fromtimestamp(r.ts, tz=timezone.utc), r.open, r.high,
                       r.low, r.close, r.volume) for r in rows]

    # ----- trades (cache for volume reconstruction) --------------------------

    def insert_trades(self, condition_id: str, raw_trades: Iterable[dict]) -> int:
        rows = []
        for t in raw_trades:
            ts, size = t.get("timestamp"), t.get("size")
            if ts is None or size is None:
                continue
            try:
                rows.append({"trade_key": _trade_key(t), "condition_id": condition_id,
                             "asset": str(t.get("asset") or ""), "timestamp": int(ts),
                             "size": float(size), "price": float(t.get("price") or 0.0),
                             "side": str(t.get("side") or "")})
            except (TypeError, ValueError):
                continue
        return self._upsert(l1_trades, rows, index=["trade_key"])   # dedupe, ignore dups

    def trade_coverage(self, condition_id: str) -> int | None:
        """Oldest timestamp we've fetched /trades down to (a fetch watermark).

        Tracked separately from the oldest *trade* so a market with no early
        trades isn't re-fetched every run.
        """
        with self.engine.connect() as cx:
            r = cx.execute(select(l1_trade_coverage.c.min_fetched)
                           .where(l1_trade_coverage.c.condition_id == condition_id)).fetchone()
        return r[0] if r else None

    def mark_trade_coverage(self, condition_id: str, min_ts: int) -> None:
        existing = self.trade_coverage(condition_id)
        new = min(existing, min_ts) if existing is not None else min_ts
        self._upsert(l1_trade_coverage, [{"condition_id": condition_id, "min_fetched": new}],
                     index=["condition_id"], update=["min_fetched"])

    def trade_ts_range(self, condition_id: str) -> tuple[int, int] | None:
        with self.engine.connect() as cx:
            r = cx.execute(select(func.min(l1_trades.c.timestamp), func.max(l1_trades.c.timestamp))
                           .where(l1_trades.c.condition_id == condition_id)).fetchone()
        return (r[0], r[1]) if r and r[0] is not None else None

    def fetch_trades(self, condition_id: str, min_ts: int | None = None,
                     max_ts: int | None = None, asset: str | None = None) -> list[dict]:
        q = select(l1_trades.c.asset, l1_trades.c.timestamp, l1_trades.c.size,
                   l1_trades.c.price, l1_trades.c.side).where(l1_trades.c.condition_id == condition_id)
        if asset is not None:
            q = q.where(l1_trades.c.asset == asset)
        if min_ts is not None:
            q = q.where(l1_trades.c.timestamp >= min_ts)
        if max_ts is not None:
            q = q.where(l1_trades.c.timestamp <= max_ts)
        q = q.order_by(l1_trades.c.timestamp)
        with self.engine.connect() as cx:
            return [{"asset": a, "timestamp": t, "size": s, "price": p, "side": sd}
                    for a, t, s, p, sd in cx.execute(q).fetchall()]

    # ----- order book snapshots ---------------------------------------------

    def record_orderbook(self, token_id: str, data: dict, ts: str | None = None) -> None:
        ts = ts or _now()
        self._upsert(l1_orderbook, [{
            "token_id": token_id, "ts": ts, "best_bid": data.get("best_bid"),
            "best_ask": data.get("best_ask"), "mid": data.get("mid"),
            "micro_price": data.get("micro_price"), "spread_bps": data.get("spread_bps"),
            "book_pressure": data.get("book_pressure"),
            "data": json.dumps(data, ensure_ascii=False),
        }], index=["token_id", "ts"],
            update=["best_bid", "best_ask", "mid", "micro_price", "spread_bps",
                    "book_pressure", "data"])

    # ----- collections (full raw bundle per run) -----------------------------

    def record_collection(self, token_id: str, as_of: str, question: str,
                          market_price: float, raw: dict) -> None:
        self._upsert(l1_collections, [{
            "token_id": token_id, "as_of": as_of, "question": question,
            "market_price": market_price, "raw": json.dumps(raw, ensure_ascii=False),
        }], index=["token_id", "as_of"], update=["question", "market_price", "raw"])

    def collection_exists(self, token_id: str, as_of: str) -> bool:
        with self.engine.connect() as cx:
            r = cx.execute(select(l1_collections.c.token_id).where(
                (l1_collections.c.token_id == token_id) & (l1_collections.c.as_of == as_of))).fetchone()
        return r is not None

    def fetch_collections(self, min_as_of: str | None = None, max_as_of: str | None = None,
                          limit: int = 500) -> list[dict]:
        """Return stored collection runs for research/backtest consumers."""
        q = select(l1_collections.c.token_id, l1_collections.c.as_of, l1_collections.c.question,
                   l1_collections.c.market_price, l1_collections.c.raw)
        if min_as_of is not None:
            q = q.where(l1_collections.c.as_of >= min_as_of)
        if max_as_of is not None:
            q = q.where(l1_collections.c.as_of <= max_as_of)
        q = q.order_by(l1_collections.c.as_of).limit(limit)
        with self.engine.connect() as cx:
            rows = cx.execute(q).fetchall()
        return [{"token_id": r.token_id, "as_of": r.as_of, "question": r.question,
                 "market_price": r.market_price, "raw": json.loads(r.raw or "{}")} for r in rows]

    # ----- introspection -----------------------------------------------------

    def counts(self) -> dict[str, int]:
        logical = {"markets": l1_markets, "candles": l1_candles, "trades": l1_trades,
                   "orderbook_snapshots": l1_orderbook, "collections": l1_collections}
        out: dict[str, int] = {}
        with self.engine.connect() as cx:
            for name, tbl in logical.items():
                out[name] = cx.execute(select(func.count()).select_from(tbl)).scalar() or 0
        return out
