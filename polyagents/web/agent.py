"""The chat agent behind the web UI — Claude + polyagents trading tools.

A self-hosted alternative to running polyagents inside an Alpha DevBox shell:
the same MCP tools (`polyagents/mcp_server.py`) are bound to a Claude ReAct
agent, and the `polymarket-trading` SKILL.md is its system prompt. The web
server streams this agent's tokens + tool calls to the browser.

Needs ``ANTHROPIC_API_KEY`` (the agent reasons via Claude); the tools themselves
are deterministic / paper-only.
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import StructuredTool

from polyagents import mcp_server
from polyagents.default_config import DEFAULT_CONFIG

# Reuse the exact MCP tool functions so the web agent and an Alpha DevBox host
# expose an identical surface (one source of truth).
_TOOL_FUNCS = [
    mcp_server.scan_markets,
    mcp_server.market_snapshot,
    mcp_server.find_similar_markets,
    mcp_server.size_position,
    mcp_server.paper_execute,
    mcp_server.portfolio_status,
    mcp_server.settle_markets,
    mcp_server.pnl_report,
    mcp_server.evaluation_report,
]


def build_tools() -> list:
    return [StructuredTool.from_function(fn) for fn in _TOOL_FUNCS]


def system_prompt() -> str:
    """The polymarket-trading SKILL.md body (frontmatter stripped)."""
    p = Path(__file__).resolve().parents[2] / "skills" / "polymarket-trading" / "SKILL.md"
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return "You are a disciplined Polymarket trading assistant. Use the tools provided."
    if text.startswith("---"):
        text = text.split("---", 2)[-1]
    return text.strip()


def build_agent(llm=None):
    """Compile the ReAct agent (Claude + tools + SKILL system prompt)."""
    from langgraph.prebuilt import create_react_agent

    if llm is None:
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            model=DEFAULT_CONFIG["anthropic_model"],
            temperature=DEFAULT_CONFIG.get("anthropic_temperature", 0.0),
        )
    return create_react_agent(llm, build_tools(), prompt=system_prompt())
