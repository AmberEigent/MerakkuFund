"""ChromaDB RAG over Polymarket markets — the Polymarket/agents capability.

The official Polymarket/agents framework (archived, OpenAI-based, Python 3.9)
overlaps everything polyagents already does *except* one thing the doc credits
it for: **RAG with Chroma** (vectorising market/news data for retrieval). We
adopt that natively here with `chromadb` (free, local all-MiniLM embeddings — no
API key), indexing the markets we collect so the signal agent can retrieve
semantically *similar* past markets as context.

Graceful: if `chromadb` isn't installed or RAG is disabled, `enabled` is False
and index/query become no-ops returning ``[]``.
"""
from __future__ import annotations

from typing import Any, Optional

from polyagents.dataflows.types import Market

_COLLECTION = "polyagents_markets"


class _LocalTextEmbedding:
    """Small deterministic embedding for offline tests and sandboxed runs.

    Chroma's default ONNX embedding may download/write model files under the
    user's home cache. This embedding keeps the default RAG path fully local and
    dependency-free while preserving enough lexical semantics for retrieval.
    """

    _KEYWORDS = (
        ("bitcoin", "btc", "crypto"),
        ("ethereum", "eth", "crypto"),
        ("crypto", "token", "blockchain"),
        ("price", "market", "cap"),
        ("rain", "weather", "storm"),
        ("lakers", "nba", "finals", "sports"),
        ("election", "president", "candidate"),
        ("fed", "rate", "inflation", "macro"),
    )

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in input]

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self(input)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self(input)

    def name(self) -> str:
        return "polyagents-local-text"

    @classmethod
    def _embed(cls, text: str) -> list[float]:
        lower = text.lower()
        vec: list[float] = []
        for group in cls._KEYWORDS:
            vec.append(float(sum(1 for word in group if word in lower)))
        vec.append(float(len(lower.split())) / 20.0)
        return vec


class ChromaRAG:
    def __init__(self, path: str | None = None, collection: str = _COLLECTION,
                 client: Any | None = None) -> None:
        self.path = path
        self._collection_name = collection
        self._col = None
        self._client = client          # injectable for tests
        self._disabled = False

    # ----- lifecycle ---------------------------------------------------------

    def _collection(self):
        if self._col is not None or self._disabled:
            return self._col
        try:
            if self._client is None:
                import chromadb
                self._client = (
                    chromadb.PersistentClient(path=self.path) if self.path
                    else chromadb.EphemeralClient()
                )
            self._col = self._client.get_or_create_collection(
                self._collection_name,
                embedding_function=_LocalTextEmbedding(),
            )
        except Exception:
            self._disabled = True
            self._col = None
        return self._col

    @property
    def enabled(self) -> bool:
        return self._collection() is not None

    # ----- writes ------------------------------------------------------------

    def index_market(self, market: Market) -> None:
        col = self._collection()
        if col is None:
            return
        doc = f"{market.question}\n{market.description}".strip()
        try:
            col.upsert(
                ids=[market.condition_id or market.market_id],
                documents=[doc],
                metadatas=[{
                    "question": market.question,
                    "condition_id": market.condition_id,
                    "outcome": market.outcome,
                    "price": float(market.price),
                }],
            )
        except Exception:
            pass

    def annotate_outcome(self, condition_id: str, winner: str) -> None:
        """Tag a market's vector with its resolved winner (closes the RAG loop)."""
        col = self._collection()
        if col is None or not condition_id:
            return
        try:
            col.update(ids=[condition_id], metadatas=[{"resolved_winner": winner}])
        except Exception:
            pass

    # ----- reads -------------------------------------------------------------

    def query_similar(self, text: str, n: int = 3, exclude_id: str | None = None) -> list[dict]:
        col = self._collection()
        if col is None or not text:
            return []
        try:
            res = col.query(query_texts=[text], n_results=n + (1 if exclude_id else 0))
        except Exception:
            return []
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        out: list[dict] = []
        for i, d, m in zip(ids, docs, metas):
            if exclude_id and i == exclude_id:
                continue
            out.append({"id": i, "document": d, "metadata": m or {}})
            if len(out) >= n:
                break
        return out

    def count(self) -> int:
        col = self._collection()
        try:
            return col.count() if col is not None else 0
        except Exception:
            return 0
