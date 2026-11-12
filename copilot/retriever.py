"""Step 2 of RAG: find the chunks most similar to a question (cosine similarity, plain numpy)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from copilot import config


class Retriever:
    def __init__(self, vectors: np.ndarray, chunks: list[dict], embedder):
        self.vectors = vectors
        self.chunks = chunks
        self.embedder = embedder

    @classmethod
    def load(cls, embedder, index_dir: Path = config.INDEX_DIR) -> "Retriever":
        vectors = np.load(index_dir / "vectors.npy")
        meta = json.loads((index_dir / "chunks.json").read_text(encoding="utf-8"))
        return cls(vectors, meta["chunks"], embedder)

    def search(self, query: str, k: int = config.TOP_K, min_score: float = config.MIN_SCORE) -> list[dict]:
        q = np.array(self.embedder.embed_query(query), dtype=np.float32)
        q /= max(np.linalg.norm(q), 1e-12)
        scores = self.vectors @ q  # vectors are pre-normalised, so dot product == cosine similarity
        top = np.argsort(-scores)[:k]
        return [{**self.chunks[i], "score": round(float(scores[i]), 3)} for i in top if scores[i] >= min_score]


def format_context(hits: list[dict]) -> str:
    """Render retrieved chunks with a citation label the model must reuse."""
    if not hits:
        return "NO_RELEVANT_POLICY_FOUND"
    return "\n\n".join(f"[{h['source']} p.{h['page']}]\n{h['text']}" for h in hits)
