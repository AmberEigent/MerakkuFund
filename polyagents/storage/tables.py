"""Table registry — the ONE place table names are defined.

Per the team's DB convention: every table is prefixed ``aihf_`` for project
isolation, and code references these Table objects / the name helpers here —
**never hard-coded name strings**. Configurable via env:

* ``AIHF_TABLE_PREFIX``  (default ``aihf_``)
* ``AIHF_DB_SCHEMA``     (Postgres schema for isolation; unset/None on SQLite)

Defined with SQLAlchemy Core so the same definitions run on SQLite (dev/tests)
and PostgreSQL (prod) — integer PKs become AUTOINCREMENT or IDENTITY per dialect.
"""
from __future__ import annotations

import os

from sqlalchemy import (Column, Float, Index, Integer, MetaData,
                        PrimaryKeyConstraint, Table, Text)

TABLE_PREFIX = os.getenv("AIHF_TABLE_PREFIX", "aihf_")
DB_SCHEMA = os.getenv("AIHF_DB_SCHEMA") or None      # None → default schema (works on SQLite)


def table_name(base: str) -> str:
    """The configured physical table name for a logical base name."""
    return f"{TABLE_PREFIX}{base}"


metadata = MetaData(schema=DB_SCHEMA)

# ----- objects + promotions (was objects_store.py's raw schema) --------------

objects = Table(
    table_name("objects"), metadata,
    Column("id", Text, primary_key=True),
    Column("type", Text), Column("version", Integer), Column("state", Text),
    Column("owner", Text), Column("snapshot_id", Text),
    Column("created_at", Text), Column("updated_at", Text),
    Column("payload_json", Text),
    Index(f"ix_{table_name('objects')}_type_state", "type", "state"),
)

promotion_events = Table(
    table_name("promotion_events"), metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("object_id", Text), Column("from_state", Text), Column("to_state", Text),
    Column("promoted_by", Text), Column("evidence_ref", Text), Column("promoted_at", Text),
    Index(f"ix_{table_name('promotion_events')}_object", "object_id"),
)

# ----- audit (was audit_store.py's raw schema) -------------------------------

audit_events = Table(
    table_name("audit_events"), metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", Text), Column("ts", Text), Column("mode", Text),
    Column("event_type", Text), Column("payload_json", Text),
    Index(f"ix_{table_name('audit_events')}_session", "session_id"),
    Index(f"ix_{table_name('audit_events')}_ts", "ts"),
)

# ----- Layer-1 data cache (was storage/db.py's raw sqlite3 schema) -----------
# The market/candle/trade/orderbook/collection cache. On SQLite (dev) it's a
# local file; with POLYAGENTS_DATABASE_URL set it lives in the shared cloud
# Postgres, so live fetches written through accumulate across every instance.

l1_markets = Table(
    table_name("markets"), metadata,
    Column("token_id", Text), Column("condition_id", Text), Column("market_id", Text),
    Column("question", Text), Column("outcome", Text), Column("price", Float),
    Column("volume_24h", Float), Column("liquidity", Float), Column("spread", Float),
    Column("days_to_expiry", Float), Column("expiry", Text), Column("fetched_at", Text),
    PrimaryKeyConstraint("token_id", "fetched_at"),
)

l1_candles = Table(
    table_name("candles"), metadata,
    Column("token_id", Text), Column("ts", Integer),
    Column("open", Float), Column("high", Float), Column("low", Float),
    Column("close", Float), Column("volume", Float), Column("fetched_at", Text),
    PrimaryKeyConstraint("token_id", "ts"),
)

l1_trades = Table(
    table_name("trades"), metadata,
    Column("trade_key", Text, primary_key=True),
    Column("condition_id", Text), Column("asset", Text), Column("timestamp", Integer),
    Column("size", Float), Column("price", Float), Column("side", Text),
    Index(f"ix_{table_name('trades')}_cond_ts", "condition_id", "timestamp"),
)

l1_trade_coverage = Table(
    table_name("trade_coverage"), metadata,
    Column("condition_id", Text, primary_key=True),
    Column("min_fetched", Integer),
)

l1_orderbook = Table(
    table_name("orderbook_snapshots"), metadata,
    Column("token_id", Text), Column("ts", Text),
    Column("best_bid", Float), Column("best_ask", Float), Column("mid", Float),
    Column("micro_price", Float), Column("spread_bps", Float), Column("book_pressure", Float),
    Column("data", Text),
    PrimaryKeyConstraint("token_id", "ts"),
)

l1_predictions = Table(
    table_name("predictions"), metadata,
    Column("id", Text, primary_key=True),
    Column("token_id", Text), Column("condition_id", Text),
    Column("question", Text), Column("category", Text),
    Column("user_p", Float), Column("market_p", Float), Column("note", Text),
    Column("created_at", Text),
    Column("resolved", Integer), Column("outcome", Integer),
    Column("brier_user", Float), Column("brier_market", Float), Column("settled_at", Text),
    Index(f"ix_{table_name('predictions')}_resolved", "resolved"),
)

l1_collections = Table(
    table_name("collections"), metadata,
    Column("token_id", Text), Column("as_of", Text), Column("question", Text),
    Column("market_price", Float), Column("raw", Text),
    PrimaryKeyConstraint("token_id", "as_of"),
)
