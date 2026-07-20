"""Create a manual live-validation trade ticket.

This helper is intentionally small: Lab remains dry-run, and the operator records
any real Polymarket trade manually before/after placing it in the venue UI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_OUT_DIR = Path("storage/manual_trade_tickets")
MAX_SIZE_USDC = 20.0


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _prompt(label: str, default: str | None = None, *, required: bool = True) -> str:
    suffix = f" [{default}]" if default not in (None, "") else ""
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if not value and default is not None:
            value = default
        if value or not required:
            return value
        print("Required field.")


def _as_float(value: str | float | None, field: str, *, required: bool = True) -> float | None:
    if value in (None, ""):
        if required:
            raise ValueError(f"{field} is required")
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a number") from exc


def _validate_probability(value: float | None, field: str) -> None:
    if value is None:
        return
    if not 0 < value < 1:
        raise ValueError(f"{field} must be between 0 and 1")


def _ticket_id(payload: dict[str, Any]) -> str:
    seed = "|".join(
        str(payload.get(key, ""))
        for key in ("created_at", "market_token_id", "side", "entry_price", "size_usdc")
    )
    return "mt_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]


def build_ticket(args: argparse.Namespace) -> dict[str, Any]:
    created_at = args.created_at or _now()
    side = (args.side or "").lower()
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")

    entry_price = _as_float(args.entry_price, "entry_price")
    max_entry_price = _as_float(args.max_entry_price, "max_entry_price", required=False)
    min_edge = _as_float(args.min_edge, "min_edge", required=False)
    size_usdc = _as_float(args.size_usdc, "size_usdc")
    exit_price = _as_float(args.exit_price, "exit_price", required=False)

    _validate_probability(entry_price, "entry_price")
    _validate_probability(max_entry_price, "max_entry_price")
    _validate_probability(exit_price, "exit_price")

    if size_usdc is None or size_usdc <= 0:
        raise ValueError("size_usdc must be positive")
    if size_usdc > MAX_SIZE_USDC:
        raise ValueError(f"size_usdc must be <= {MAX_SIZE_USDC:.0f} for manual live validation")
    if max_entry_price is not None and entry_price is not None and side == "buy" and entry_price > max_entry_price:
        raise ValueError("entry_price is above max_entry_price; do not execute this ticket")

    shares = round(size_usdc / entry_price, 6) if side == "buy" and entry_price else None
    realized_pnl = None
    if exit_price is not None and shares is not None:
        realized_pnl = round((exit_price - entry_price) * shares, 4)

    ticket: dict[str, Any] = {
        "ticket_id": "",
        "created_at": created_at,
        "status": args.status,
        "mode": "manual_live_validation",
        "risk_limits": {
            "max_size_usdc": MAX_SIZE_USDC,
            "auto_execution": False,
            "operator_must_confirm_price": True,
        },
        "signal": {
            "source": args.signal_source,
            "strategy_id": args.strategy_id,
            "hypothesis_id": args.hypothesis_id or None,
            "report_id": args.report_id or None,
            "monitor_snapshot": args.monitor_snapshot or None,
            "p_cal": _as_float(args.p_cal, "p_cal", required=False),
            "market_price_at_signal": _as_float(args.market_price_at_signal, "market_price_at_signal", required=False),
            "edge": min_edge,
            "trigger_rule": args.trigger_rule,
        },
        "market": {
            "question": args.question,
            "market_url": args.market_url or None,
            "market_token_id": args.market_token_id,
            "outcome": args.outcome,
            "category": args.category or None,
        },
        "execution": {
            "side": side,
            "size_usdc": round(size_usdc, 2),
            "entry_price": entry_price,
            "max_entry_price": max_entry_price,
            "estimated_shares": shares,
            "executed_at": args.executed_at or created_at,
            "venue": "polymarket",
            "manual_operator": args.operator or None,
        },
        "exit_plan": {
            "plan": args.exit_plan,
            "stop_price": _as_float(args.stop_price, "stop_price", required=False),
            "take_profit_price": _as_float(args.take_profit_price, "take_profit_price", required=False),
            "exit_price": exit_price,
            "realized_pnl_usdc": realized_pnl,
        },
        "evidence": {
            "screenshot_path": args.screenshot_path or None,
            "notes": args.notes or None,
        },
    }
    ticket["ticket_id"] = args.ticket_id or _ticket_id(ticket | {"market_token_id": args.market_token_id})
    return ticket


def write_ticket(ticket: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ticket['ticket_id']}.json"
    path.write_text(json.dumps(ticket, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (out_dir / "manual_trade_tickets.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ticket, ensure_ascii=False) + "\n")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a manual Polymarket trade ticket.")
    parser.add_argument("--interactive", action="store_true", help="Prompt for missing fields.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--ticket-id", default="")
    parser.add_argument("--created-at", default="")
    parser.add_argument("--status", default="open", choices=["planned", "open", "closed", "cancelled"])
    parser.add_argument("--signal-source", default="lab-monitor", choices=["lab-monitor", "lab-backtest", "ask-scan", "manual"])
    parser.add_argument("--strategy-id", default="momentum-v1")
    parser.add_argument("--hypothesis-id", default="")
    parser.add_argument("--report-id", default="")
    parser.add_argument("--monitor-snapshot", default="")
    parser.add_argument("--p-cal", default="")
    parser.add_argument("--market-price-at-signal", default="")
    parser.add_argument("--min-edge", default="")
    parser.add_argument("--trigger-rule", default="BUY only if current price <= max_entry_price and edge remains positive.")
    parser.add_argument("--question", default="")
    parser.add_argument("--market-url", default="")
    parser.add_argument("--market-token-id", default="")
    parser.add_argument("--outcome", default="YES")
    parser.add_argument("--category", default="")
    parser.add_argument("--side", default="buy")
    parser.add_argument("--size-usdc", default="10")
    parser.add_argument("--entry-price", default="")
    parser.add_argument("--max-entry-price", default="")
    parser.add_argument("--executed-at", default="")
    parser.add_argument("--operator", default="")
    parser.add_argument("--exit-plan", default="Hold until resolution unless edge disappears or price breaches stop.")
    parser.add_argument("--stop-price", default="")
    parser.add_argument("--take-profit-price", default="")
    parser.add_argument("--exit-price", default="")
    parser.add_argument("--screenshot-path", default="")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    if args.interactive:
        args.question = args.question or _prompt("Market question")
        args.market_token_id = args.market_token_id or _prompt("Market token id")
        args.outcome = args.outcome or _prompt("Outcome", "YES")
        args.side = args.side or _prompt("Side", "buy")
        args.size_usdc = args.size_usdc or _prompt("Size USDC", "10")
        args.entry_price = args.entry_price or _prompt("Actual entry price, 0-1")
        args.max_entry_price = args.max_entry_price or _prompt("Max allowed entry price, 0-1", "", required=False)
        args.min_edge = args.min_edge or _prompt("Signal edge, e.g. 0.06", "", required=False)
        args.strategy_id = args.strategy_id or _prompt("Strategy id", "momentum-v1")
        args.report_id = args.report_id or _prompt("Report id", "", required=False)
        args.market_url = args.market_url or _prompt("Polymarket URL", "", required=False)
        args.screenshot_path = args.screenshot_path or _prompt("Screenshot path", "", required=False)
        args.notes = args.notes or _prompt("Notes", "", required=False)
    return args


def main() -> int:
    args = parse_args()
    required = {
        "question": args.question,
        "market_token_id": args.market_token_id,
        "entry_price": args.entry_price,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise SystemExit(f"Missing required fields: {', '.join(missing)}. Use --interactive to fill them.")
    ticket = build_ticket(args)
    path = write_ticket(ticket, Path(args.out_dir))
    print(f"wrote {path}")
    print(json.dumps(ticket, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
