import hashlib
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel  # noqa: E402


class HashEmbedder:
    """Offline stand-in for OpenAI embeddings: hashed bag-of-words, good enough for keyword retrieval tests."""
    dims = 512

    def _embed(self, text: str) -> list[float]:
        v = np.zeros(self.dims, dtype=np.float32)
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dims] += 1
        return v.tolist()

    def embed_documents(self, texts):
        return [self._embed(t) for t in texts]

    def embed_query(self, text):
        return self._embed(text)


class ScriptedToolModel(GenericFakeChatModel):
    """Fake chat model that replays scripted AIMessages (including tool calls) and accepts bind_tools."""

    def bind_tools(self, tools, **kwargs):
        return self


@pytest.fixture
def embedder():
    return HashEmbedder()


@pytest.fixture
def index_dir(tmp_path, embedder):
    from copilot.ingest import build_index

    out = tmp_path / "index"
    build_index(ROOT / "data" / "policies", out, embedder=embedder, embedding_model="hash-test")
    return out


@pytest.fixture
def retriever(index_dir, embedder):
    from copilot.retriever import Retriever

    return Retriever.load(embedder, index_dir)


@pytest.fixture
def store(tmp_path):
    from copilot.hr_store import HRStore

    records = tmp_path / "hr_records.json"
    shutil.copy(ROOT / "data" / "hr_records.json", records)
    return HRStore(records_path=records, requests_path=tmp_path / "requests.json")
