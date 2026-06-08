"""Settlement — turn a resolved Polymarket market into realised P&L.

When a market closes, its winning token pays $1 and the loser $0. We read the
resolution from Gamma (``closed`` + ``outcomePrices``), then settle the paper
position: a held side that won closes at 1.0, a loser at 0.0. This is the
"realised return" the feedback loop reflects on.

Pure helpers here; the orchestrator drives the loop over open positions.
"""
from __future__ import annotations

from typing import Optional

from polyagents.dataflows.utils import parse_json_field


def _winning_index(market_raw: dict) -> Optional[int]:
    if not market_raw or not market_raw.get("closed"):
        return None
    try:
        prices = [float(p) for p in parse_json_field(market_raw.get("outcomePrices") or [])]
    except (TypeError, ValueError):
        return None
    if not prices:
        return None
    idx = max(range(len(prices)), key=lambda i: prices[i])
    return idx if prices[idx] >= 0.99 else None   # cleanly resolved only


def resolve_winner(market_raw: dict) -> Optional[str]:
    """Winning side as a best-effort 'YES'/'NO' label (for display)."""
    idx = _winning_index(market_raw)
    outcomes = parse_json_field(market_raw.get("outcomes")) if idx is not None else []
    if idx is None or idx >= len(outcomes):
        return None
    label = str(outcomes[idx]).strip().lower()
    return "YES" if label in {"yes", "true"} else "NO"


def resolve_winning_token(market_raw: dict) -> Optional[str]:
    """The winning side's CLOB token id — the robust resolution key.

    Many markets use custom outcome labels (player/candidate names), so a
    YES/NO label is lossy; settle by token id instead.
    """
    idx = _winning_index(market_raw)
    tokens = parse_json_field(market_raw.get("clobTokenIds")) if idx is not None else []
    if idx is None or idx >= len(tokens):
        return None
    return str(tokens[idx])


def settlement_pnl(won: bool, shares: float, avg_price: float) -> float:
    """Paper payout: winner pays $1/share, loser $0."""
    payout = 1.0 if won else 0.0
    return (payout - avg_price) * shares
