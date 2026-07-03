"""Real wiring for the kernel — a registry backed by the live engine, Lab
BacktestRunner, the Ask LangGraph agent, and the Strategy supervisor.

Lazy + best-effort (imports and the engine are only touched when built), so the
kernel core stays import-light and offline-testable (tests inject fakes; this is
the production wiring). Needs network / ANTHROPIC_API_KEY at run time.
"""
from __future__ import annotations

from .capabilities import (analyze_market_capability, answer_capability,
                           backtest_capability, batch_backtest_capability,
                           batch_collect_capability, data_capability,
                           domain_capability, resolve_market_capability,
                           scan_capability, strategy_capability)


def _chunk_text(content) -> str:
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return content if isinstance(content, str) else str(content or "")


def _stream_agent(agent, question: str, emit) -> str:
    """Drive a LangGraph agent's ``astream_events`` in a fresh loop, emitting inner
    tokens/tool-calls via ``emit`` as they happen, and return the full text. Runs in
    the kernel's worker thread (no running loop there), so ``asyncio.run`` is safe."""
    import asyncio

    async def drive() -> str:
        parts: list[str] = []
        async for ev in agent.astream_events(
                {"messages": [("user", question or "")]}, version="v2"):
            kind = ev.get("event")
            if kind == "on_chat_model_stream":
                t = _chunk_text(ev["data"]["chunk"].content)
                if t:
                    parts.append(t)
                    emit({"type": "token", "text": t})
            elif kind == "on_tool_start":
                emit({"type": "tool", "name": ev.get("name")})
            elif kind == "on_tool_end":
                emit({"type": "tool_result", "name": ev.get("name")})
        return "".join(parts)

    return asyncio.run(drive())


def default_registry() -> list:
    """Wire data → backtest (over resolved markets), plus answer + strategy.

    ``event`` is treated as a free-text handle; we slice resolved markets by its
    keyword category, then replay a deterministic backtest over them."""
    from polyagents import mcp_server
    from polyagents.evaluation.evaluate import categorize
    from polyagents.lab.backtest import BacktestRunner

    eng = mcp_server.engine()

    def _resolved_yes(query):
        """Resolved YES-side markets, sliced to the request's keyword category."""
        cat = categorize(query or "")
        raw = eng.client.list_resolved_markets(limit=80)
        yes = [m for m in eng.client.to_markets(raw) if m.outcome == "YES"]
        if cat != "other":
            yes = [m for m in yes if categorize(m.question) == cat]
        return cat, yes

    def fetch(event):
        cat, yes = _resolved_yes(event)
        return {"event": event, "category": cat, "markets": yes}

    def _replay(markets, event=None):
        out = BacktestRunner(client=eng.client, max_markets=20).replay(
            category=None, markets=markets)
        s = out["summary"]
        return {"event": event, "n_markets": out["n_markets"],
                "brier_delta": s.brier_delta, "beats_market": s.beats_market,
                "ci": list(s.brier_delta_ci)}

    def backtest(history):
        return _replay(history["markets"], event=history.get("event"))

    # ----- batch data pipeline (scan -> collect / backtest) ------------------

    def scan(query):
        rows = mcp_server.scan_markets(limit=8, min_volume_24h=20000.0)
        return {"query": query, "count": len(rows), "markets": rows}

    def batch_collect(market_batch, cap=5):
        rows = (market_batch or {}).get("markets", [])[:cap]
        collected = []
        for row in rows:
            m = mcp_server._get_market(row.get("token_id", ""))
            if m is None:
                continue
            eng.collect(m)
            collected.append(row.get("question") or row.get("token_id"))
        counts = eng.store.counts() if getattr(eng, "store", None) else {}
        return {"n_markets": len(collected), "collected": collected,
                "store_counts": counts}

    def batch_backtest(query):
        _cat, yes = _resolved_yes(query)
        return _replay(yes, event=query)

    # ----- Goal 1: single-target analysis framework --------------------------
    #   resolve_market -> analyze_market
    #   explore -> reason -> analyze -> backtest (historical comparison) -> conclude

    def resolve(query):
        """Pick ONE concrete market for the request: explicit token id, else best
        keyword match among live markets, else the most active."""
        q = (query or "").strip()
        m = mcp_server._get_market(q) if q else None      # exact token id?
        if m is None:
            rows = mcp_server.scan_markets(limit=25, min_volume_24h=0.0)
            words = {w for w in q.lower().split() if len(w) > 2}
            best, best_hits = None, 0
            for row in rows:
                hits = sum(1 for w in words if w in str(row.get("question", "")).lower())
                if hits > best_hits:
                    best, best_hits = row, hits
            if best is not None:
                return {"token_id": best["token_id"], "question": best["question"],
                        "price": best["price"], "matched_by": f"keywords({best_hits})"}
            m = eng.most_active_market()                   # nothing matched
        if m is None:
            return {"error": "no market found", "query": query}
        return {"token_id": m.token_id, "question": m.question, "price": m.price,
                "matched_by": "token_id" if q == m.token_id else "most_active"}

    def analyze_market(market_ref):
        """Run the whole Goal-1 framework on one market and return a structured result."""
        ref = market_ref or {}
        token = ref.get("token_id")
        m = mcp_server._get_market(token) if token else None
        if m is None:
            return {"error": f"market not found: {ref}", "market_ref": ref}

        state = eng.analyze(m)                              # L1 collect + L2 signal/decision/reflect (LLM)
        sig = state.get("signal")
        dec = state.get("trade_decision")
        refl = state.get("reflection")
        factors = ((state.get("raw", {}) or {}).get("features", {}) or {}).get("factors", {})

        cat, yes = _resolved_yes(m.question)               # 回溯对比: backtest the signal on comparable history
        backtest = _replay(yes, event=m.question) if yes else {
            "n_markets": 0, "note": f"no resolved '{cat}' markets to backtest against"}

        try:
            similar = mcp_server.find_similar_markets(m.question, n=3)
        except Exception:
            similar = []

        return {
            "market": {"token_id": m.token_id, "question": m.question, "price": m.price,
                       "category": cat, "days_to_expiry": round(m.days_to_expiry, 1),
                       "liquidity": m.liquidity},
            "explore": {"price_report": state.get("price_report"),
                        "orderbook_report": state.get("orderbook_report"),
                        "trades_flow_report": state.get("trades_flow_report")},
            "microstructure": factors,
            "reasoning": ({"p_true": sig.p_true, "direction": sig.direction,
                           "conviction": sig.conviction, "rationale": sig.rationale}
                          if sig is not None else {"note": "no signal (LLM unavailable)"}),
            "backtest": backtest,
            "similar_markets": similar,
            "conclusion": ({"action": dec.action, "edge": round(dec.edge, 4),
                            "p_calibrated": round(dec.p_true, 4),
                            "annualized_edge": round(dec.annualized_edge, 4),
                            "size_usdc": round(dec.size_usdc, 2), "reasons": dec.reasons,
                            "risk_flags": (refl.risk_flags if refl is not None else [])}
                           if dec is not None else {"note": "no decision"}),
        }

    def _last_content(res):
        msgs = res.get("messages", []) if isinstance(res, dict) else []
        last = msgs[-1] if msgs else None
        return getattr(last, "content", "") if last is not None else ""

    def answer(question):                              # general / web-search agent
        from polyagents.web.agent import build_general_agent
        return _last_content(build_general_agent().invoke(
            {"messages": [("user", question or "")]}))

    def answer_stream(question, emit):
        from polyagents.web.agent import build_general_agent
        return _stream_agent(build_general_agent(), question, emit)

    def domain_answer(question):                       # read-only market-tools agent
        from polyagents.web.agent import build_agent
        return _last_content(build_agent(readonly=True).invoke(
            {"messages": [("user", question or "")]}))

    def domain_stream(question, emit):
        from polyagents.web.agent import build_agent
        return _stream_agent(build_agent(readonly=True), question, emit)

    def run_strategy(market):
        from polyagents.orchestration import run_strategy as _rs
        bb = _rs(market, graph=eng, config=eng.config, strategy="full")
        return bb.risk

    return [
        data_capability(fetch),
        backtest_capability(backtest),
        scan_capability(scan),
        batch_collect_capability(batch_collect),
        batch_backtest_capability(batch_backtest),
        resolve_market_capability(resolve),
        analyze_market_capability(analyze_market),
        answer_capability(answer, stream_fn=answer_stream),
        domain_capability(domain_answer, stream_fn=domain_stream),
        strategy_capability(run_strategy),
    ]
