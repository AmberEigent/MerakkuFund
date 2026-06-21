"""Standalone MCP servers — pluggable, no-key tool providers for a host platform.

Each module is its own FastMCP server (register them in .mcp.json):

  * ``crypto``        — Binance public REST: cross-market crypto prices
  * ``polydata``      — Polymarket events / price history / recent trades (REST)
  * ``compliance``    — trade-math double-check + audit log + limit checks
  * ``qlib_backtest`` — factor → model → backtest over the SQLite history
                        (standalone; run with the qlib venv interpreter)

Run any of them:  ``python -m polyagents.mcp_servers.<name>`` (``--http`` optional).
"""
