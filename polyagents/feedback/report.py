"""P&L / attribution report over the decision log.

The daily-report half of Layer 4: aggregate resolved trades into hit rate, total
and average realised P&L/return, and a buy/hold/sell breakdown. Pure over a list
of memory records so it tests without state.
"""
from __future__ import annotations


def pnl_report(records: list[dict]) -> str:
    resolved = [r for r in records if r.get("status") == "resolved" and r.get("realized_pnl") is not None]
    pending = [r for r in records if r.get("status") == "pending"]
    if not resolved:
        return f"No resolved trades yet ({len(pending)} pending)."

    pnls = [float(r["realized_pnl"]) for r in resolved]
    wins = [r for r in resolved if r.get("won")]
    total = sum(pnls)
    returns = [float(r["realized_return"]) for r in resolved if r.get("realized_return") is not None]
    avg_ret = sum(returns) / len(returns) if returns else 0.0

    actions: dict[str, int] = {}
    for r in records:
        actions[r.get("action", "?")] = actions.get(r.get("action", "?"), 0) + 1

    return (
        f"P&L report — {len(resolved)} resolved, {len(pending)} pending\n"
        f"  hit rate: {len(wins)}/{len(resolved)} ({len(wins)/len(resolved):.0%})\n"
        f"  realised P&L: ${total:+,.2f}  |  avg return: {avg_ret:+.1%}\n"
        f"  best ${max(pnls):+,.2f} / worst ${min(pnls):+,.2f}\n"
        f"  decisions: " + ", ".join(f"{k} {v}" for k, v in sorted(actions.items()))
    )
