"""Personal prediction journal — the user's own subjective probability calls.

Log a call (your P + the market price at the time), and once the market resolves,
score whether your judgment beat the market (Brier). Backed by the shared engine,
so with ``POLYAGENTS_DATABASE_URL`` set the journal accumulates in the cloud DB —
forward-tracking that tells you where your subjective read actually has edge.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import insert, select, update

from .engine import coerce_url, get_engine, make_engine
from .tables import l1_predictions as predictions, metadata


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PredictionStore:
    def __init__(self, url_or_path: str | None = None, *, engine=None) -> None:
        if engine is not None:
            self.engine = engine
        elif url_or_path is None:
            self.engine = get_engine()
        else:
            self.engine = make_engine(coerce_url(str(url_or_path)))
        metadata.create_all(self.engine, tables=[predictions])

    def close(self) -> None:
        self.engine.dispose()

    def log(self, *, token_id: str, condition_id: str, question: str, category: str,
            user_p: float, market_p: float, note: str = "") -> dict:
        row = {"id": f"pred_{uuid.uuid4().hex[:10]}", "token_id": token_id,
               "condition_id": condition_id, "question": question, "category": category,
               "user_p": user_p, "market_p": market_p, "note": note, "created_at": _now(),
               "resolved": 0, "outcome": None, "brier_user": None, "brier_market": None,
               "settled_at": None}
        with self.engine.begin() as cx:
            cx.execute(insert(predictions).values(**row))
        return row

    def open(self) -> list[dict]:
        with self.engine.connect() as cx:
            return [dict(r) for r in cx.execute(
                select(predictions).where(predictions.c.resolved == 0)).mappings().fetchall()]

    def all(self) -> list[dict]:
        with self.engine.connect() as cx:
            return [dict(r) for r in cx.execute(
                select(predictions).order_by(predictions.c.created_at.desc())).mappings().fetchall()]

    def mark_resolved(self, pid: str, outcome: int, brier_user: float, brier_market: float) -> None:
        with self.engine.begin() as cx:
            cx.execute(update(predictions).where(predictions.c.id == pid).values(
                resolved=1, outcome=int(outcome), brier_user=brier_user,
                brier_market=brier_market, settled_at=_now()))
