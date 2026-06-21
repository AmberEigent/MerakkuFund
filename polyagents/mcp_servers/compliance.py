"""Compliance / math-verification MCP (no key).

The Merakku doc's financial-services-plugins layer: independent math
double-check + limit/compliance checks + an audit trail. Before acting on a
sized trade, the agent calls ``verify_trade_math`` to confirm the numbers were
computed correctly and sit within the configured risk limits — a guard against
LLM arithmetic slips and limit breaches. Native, deterministic, no key.
"""
from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP

from polyagents.agents.risk import annualized_edge, edge_for_side, kelly_fraction
from polyagents.default_config import DEFAULT_CONFIG
from polyagents.feedback.memory import MemoryStore

mcp = FastMCP("compliance")
_cfg = DEFAULT_CONFIG


@mcp.tool()
def verify_trade_math(p_true: float, market_price: float, size_usdc: float,
                      days_to_expiry: float = 30.0, bankroll: float | None = None) -> dict:
    """Independently recompute edge / Kelly / APY / position-fraction and flag any
    inconsistency or limit breach. Returns pass=False with flags if something's off."""
    bankroll = bankroll or _cfg["bankroll_usdc"]
    edge = edge_for_side(p_true, market_price)
    apy = annualized_edge(edge, market_price, days_to_expiry)
    f = min(kelly_fraction(p_true, market_price) * _cfg["kelly_multiplier"], _cfg["max_position_fraction"])
    expected_size = round(f * bankroll, 2)
    pos_frac = size_usdc / bankroll if bankroll else 0.0

    flags: list[str] = []
    if pos_frac > _cfg["max_position_fraction"] + 1e-9:
        flags.append(f"position {pos_frac:.1%} exceeds cap {_cfg['max_position_fraction']:.0%}")
    if size_usdc > 0 and abs(size_usdc - expected_size) > max(0.5, 0.02 * expected_size):
        flags.append(f"size ${size_usdc:.2f} != Kelly-implied ${expected_size:.2f}")
    if size_usdc > 0 and abs(edge) < _cfg["edge_floor"]:
        flags.append(f"acting on |edge| {abs(edge):.1%} below floor {_cfg['edge_floor']:.0%}")
    if size_usdc > 0 and apy < _cfg["min_annualized_edge"]:
        flags.append(f"APY {apy:.0%} below floor {_cfg['min_annualized_edge']:.0%}")
    return {
        "edge": round(edge, 4), "annualized_edge": round(apy, 4),
        "kelly_fraction": round(f, 4), "expected_size_usdc": expected_size,
        "position_fraction": round(pos_frac, 4), "pass": not flags, "flags": flags,
    }


@mcp.tool()
def audit_log(limit: int = 20) -> list:
    """The most recent decisions from the persistent audit / decision log."""
    rows = MemoryStore(_cfg["memory_path"]).all()[-limit:]
    return [{"ts": r.get("ts"), "question": r.get("question"), "action": r.get("action"),
             "p_true": r.get("p_true"), "edge": r.get("edge"), "size_usdc": r.get("size_usdc"),
             "status": r.get("status"), "realized_pnl": r.get("realized_pnl")} for r in rows]


@mcp.tool()
def risk_limits() -> dict:
    """The configured risk limits the system enforces (for transparency / audit)."""
    return {k: _cfg[k] for k in (
        "bankroll_usdc", "edge_floor", "min_annualized_edge", "kelly_multiplier",
        "max_position_fraction", "min_liquidity_usdc", "max_spread_bps",
        "max_daily_loss_pct", "max_total_exposure_pct", "max_concurrent_positions",
    )}


def main() -> None:
    mcp.run(transport="streamable-http" if "--http" in sys.argv else "stdio")


if __name__ == "__main__":
    main()
