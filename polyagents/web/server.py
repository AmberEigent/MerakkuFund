"""FastAPI chat server — streams the polyagents trading agent to the browser.

    python -m polyagents.web            # http://127.0.0.1:8000

GET  /            → the chat UI (web/static/index.html)
POST /api/chat    → Server-Sent Events: token / tool / tool_result / done / error

The agent (Claude + polyagents tools) is built once and reused, so the paper
portfolio persists across messages. Needs ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .agent import build_agent

_STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="polyagents chat")
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

_AGENT = None


def _agent():
    global _AGENT
    if _AGENT is None:
        _AGENT = build_agent()
    return _AGENT


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(_STATIC / "index.html"))


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _text_of(content: Any) -> str:
    """Anthropic chunk content can be a string or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for blk in content:
            if isinstance(blk, dict) and blk.get("type") == "text":
                out.append(blk.get("text", ""))
            elif isinstance(blk, str):
                out.append(blk)
        return "".join(out)
    return ""


def _to_lc_messages(history: list[dict]) -> list[tuple[str, str]]:
    msgs: list[tuple[str, str]] = []
    for m in history:
        role = "assistant" if m.get("role") == "assistant" else "user"
        msgs.append((role, str(m.get("content", ""))))
    return msgs


async def _stream(history: list[dict]) -> AsyncIterator[str]:
    try:
        agent = _agent()
    except Exception as exc:
        yield _sse({"type": "error", "message": f"agent init failed: {exc}"})
        return
    messages = _to_lc_messages(history)
    try:
        async for ev in agent.astream_events({"messages": messages}, version="v2"):
            kind = ev.get("event")
            if kind == "on_chat_model_stream":
                text = _text_of(ev["data"]["chunk"].content)
                if text:
                    yield _sse({"type": "token", "text": text})
            elif kind == "on_tool_start":
                yield _sse({"type": "tool", "name": ev.get("name"), "args": ev["data"].get("input")})
            elif kind == "on_tool_end":
                yield _sse({"type": "tool_result", "name": ev.get("name")})
        yield _sse({"type": "done"})
    except Exception as exc:
        yield _sse({"type": "error", "message": str(exc)})


@app.post("/api/chat")
async def chat(request: Request) -> StreamingResponse:
    body = await request.json()
    history = body.get("messages", [])
    return StreamingResponse(_stream(history), media_type="text/event-stream")
