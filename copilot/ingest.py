"""Step 1 of RAG: turn PDFs into searchable vectors.

PDF -> pages of text -> overlapping chunks -> embeddings -> saved index (vectors.npy + chunks.json).
Run:  python -m copilot.ingest
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
from pypdf import PdfReader

from copilot import config


def load_pdf_pages(policy_dir: Path) -> list[dict]:
    pages = []
    for pdf in sorted(policy_dir.glob("*.pdf")):
        for page_no, page in enumerate(PdfReader(pdf).pages, start=1):
            text = re.sub(r"[ \t]+", " ", page.extract_text() or "").strip()
            if text:
                pages.append({"source": pdf.name, "page": page_no, "text": text})
    return pages


def chunk_text(text: str, size: int = config.CHUNK_SIZE, overlap: int = config.CHUNK_OVERLAP) -> list[str]:
    """Split on paragraph/line boundaries into ~size-char chunks with some overlap for context."""
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    parts = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    chunks, current = [], ""
    for part in parts:
        while len(part) > size:  # very long paragraph: hard split
            head, part = part[:size], part[size - overlap:]
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head)
        if current and len(current) + len(part) + 1 > size:
            chunks.append(current)
            current = current[-overlap:] if overlap else ""
            current = (current + "\n" + part).strip()
        else:
            current = (current + "\n" + part).strip()
    if current:
        chunks.append(current)
    return chunks


def corpus_fingerprint(policy_dir: Path, embedding_model: str) -> str:
    h = hashlib.sha256(embedding_model.encode())
    for pdf in sorted(policy_dir.glob("*.pdf")):
        h.update(pdf.name.encode())
        h.update(pdf.read_bytes())
    return h.hexdigest()


def get_embedder():
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(model=config.EMBEDDING_MODEL, api_key=config.OPENAI_API_KEY or None)


def normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.clip(norms, 1e-12, None)


def build_index(policy_dir: Path = config.POLICY_DIR, index_dir: Path = config.INDEX_DIR,
                embedder=None, embedding_model: str = config.EMBEDDING_MODEL) -> dict:
    embedder = embedder or get_embedder()
    chunks = []
    for page in load_pdf_pages(policy_dir):
        for i, text in enumerate(chunk_text(page["text"])):
            chunks.append({"id": f"{page['source']}#p{page['page']}-{i}", "source": page["source"],
                           "page": page["page"], "text": text})
    if not chunks:
        raise RuntimeError(f"No text found in PDFs under {policy_dir}")

    vectors = normalize(np.array(embedder.embed_documents([c["text"] for c in chunks]), dtype=np.float32))
    index_dir.mkdir(parents=True, exist_ok=True)
    np.save(index_dir / "vectors.npy", vectors)
    meta = {"embedding_model": embedding_model,
            "fingerprint": corpus_fingerprint(policy_dir, embedding_model), "chunks": chunks}
    (index_dir / "chunks.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def index_is_current(policy_dir: Path = config.POLICY_DIR, index_dir: Path = config.INDEX_DIR,
                     embedding_model: str = config.EMBEDDING_MODEL) -> bool:
    meta_path = index_dir / "chunks.json"
    if not meta_path.exists() or not (index_dir / "vectors.npy").exists():
        return False
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return meta.get("fingerprint") == corpus_fingerprint(policy_dir, embedding_model)


def ensure_index(embedder=None) -> None:
    """Build the index only when the PDFs or embedding model changed."""
    if not index_is_current():
        build_index(embedder=embedder)


if __name__ == "__main__":
    meta = build_index()
    sources = sorted({c["source"] for c in meta["chunks"]})
    print(f"Indexed {len(meta['chunks'])} chunks from {len(sources)} PDFs -> {config.INDEX_DIR}")
    for s in sources:
        print("  -", s)
