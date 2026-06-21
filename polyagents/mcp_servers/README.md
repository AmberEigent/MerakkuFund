# polyagents MCP servers (no-key)

Pluggable tool providers an Alpha DevBox-style host (or our web agent) can
connect to. All are **free / no API key**. Registered in [`.mcp.json`](../../.mcp.json).

| Server | Tools | Runs with | Notes |
|---|---|---|---|
| **polyagents** (`mcp_server.py`) | scan / snapshot / size / paper_execute / portfolio / settle / pnl / evaluation | polyagents venv | the core trading engine |
| **crypto** | `crypto_price`, `crypto_24h`, `crypto_klines` | polyagents venv | Binance public REST — cross-market signal for crypto markets |
| **polydata** | `list_events`, `recent_trades`, `price_history` | polyagents venv | Polymarket events / history / trades (REST) |
| **compliance** | `verify_trade_math`, `audit_log`, `risk_limits` | polyagents venv | independent math double-check + audit + limits |
| **qlib-backtest** | `data_summary`, `run_backtest` | **qlib venv** | factor→model→backtest over the SQLite history; leakage-safe time split |
| **polymarket-docs** | docs search / read | remote http | official Polymarket documentation MCP |

## Run one directly
```bash
python -m polyagents.mcp_servers.crypto          # stdio (default)
python -m polyagents.mcp_servers.crypto --http   # streamable-http on :8000
```

## Why qlib-backtest is special
qlib has its own venv (`C:\qlib\.venv`), so this server is **standalone** — it
imports no polyagents code, reads the SQLite DB by path, and uses the qlib venv's
pandas + lightgbm. The host launches it with the qlib interpreter (see `.mcp.json`);
`PYTHONPATH` points at the repo so `-m polyagents.mcp_servers.qlib_backtest`
resolves. Requires `mcp` installed in the qlib venv.

## Adding another MCP
Drop a `polyagents/mcp_servers/<name>.py` with `@mcp.tool()` functions and a
`main()` that calls `mcp.run(...)`, then add it to `.mcp.json`. No host change.
Pair it with a `skills/<name>/SKILL.md` so the agent knows when to use it.
