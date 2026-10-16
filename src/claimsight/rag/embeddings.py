"""Embeddings with an on-disk cache, plus a helper to free Ollama memory.

Why: a laptop with 8 GB of RAM cannot hold a 7B chat model and the embedding model at the same
time (the OOM killer stops Ollama). Query vectors are computed once while the chat model is
unloaded (`make eval-retrieval`) and reused from the cache by the coverage run, which then only
needs the chat model. A cache miss falls back to the live embedder.
"""

import hashlib
import json
from pathlib import Path

import ollama
from langchain_core.embeddings import Embeddings

CACHE_PATH = Path(".cache/claimsight/embeddings.json")


class CachedEmbeddings(Embeddings):
    def __init__(self, inner: Embeddings, model: str, path: Path = CACHE_PATH) -> None:
        self._inner, self._model, self._path = inner, model, path
        try:
            self._cache: dict[str, list[float]] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._cache = {}

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self._model}\n{text}".encode()).hexdigest()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        missing = [t for t in dict.fromkeys(texts) if self._key(t) not in self._cache]
        if missing:
            for text, vector in zip(missing, self._inner.embed_documents(missing), strict=True):
                self._cache[self._key(text)] = vector
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._cache), encoding="utf-8")
        return [self._cache[self._key(t)] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def unload_model(name: str) -> None:
    """Ask Ollama to drop a model from memory now (keep_alive=0)."""
    try:
        ollama.generate(model=name, prompt="", keep_alive=0)
    except Exception:  # best effort: a model that is not loaded or a server that is down
        pass
