"""Text embeddings for semantic search.

Two interchangeable backends:

* ``fastembed``: a real sentence-embedding model (ONNX, runs locally on CPU, no API key). The model
  file is downloaded the first time it is used.
* ``hashing``: a small deterministic, dependency-free embedder (word + character n-gram hashing).
  It needs no download, so it is used for tests and as an automatic fallback when the real model
  cannot be loaded. It captures word overlap and spelling variants, not meaning.

``EMBEDDING_BACKEND=auto`` (default) tries fastembed first and falls back to hashing. The name of the
backend that produced a vector is stored with it, and search only compares vectors from the same
backend, so switching backends never mixes incompatible vectors (run ``reindex_search`` afterwards).
"""
import hashlib
import logging
import re
import threading

import numpy as np
from django.conf import settings

logger = logging.getLogger(__name__)

WORD_RE = re.compile(r"[a-z0-9]+")


class HashingEmbedder:
    dim = 384
    name = "hashing-384"

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            counts: dict[int, float] = {}
            words = WORD_RE.findall(text.lower())
            features = list(words)
            for word in words:
                padded = f"#{word}#"
                features += [padded[i:i + 3] for i in range(len(padded) - 2)] if len(word) > 3 else []
            for feature in features:
                digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
                number = int.from_bytes(digest, "little")
                index, sign = number % self.dim, 1.0 if (number >> 40) & 1 else -1.0
                counts[index] = counts.get(index, 0.0) + sign
            for index, value in counts.items():
                out[row, index] = value
        return normalise(out)


class FastEmbedder:
    def __init__(self, model_name: str, cache_dir: str):
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir or None)
        self.name = model_name
        self.dim = len(next(iter(self._model.embed(["dimension probe"]))))

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.array(list(self._model.embed(texts)), dtype=np.float32)
        return normalise(vectors.reshape(len(texts), -1))


def normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


_lock = threading.Lock()
_cached: dict[str, object] = {}


def reset_embedder() -> None:
    _cached.clear()


def get_embedder():
    backend = (getattr(settings, "EMBEDDING_BACKEND", "auto") or "auto").lower()
    with _lock:
        if backend in _cached:
            return _cached[backend]
        embedder = None
        if backend in ("auto", "fastembed"):
            try:
                embedder = FastEmbedder(settings.EMBEDDING_MODEL, settings.EMBEDDING_CACHE_DIR)
            except Exception as exc:  # noqa: BLE001 - missing package, no network, corrupt cache...
                if backend == "fastembed":
                    raise
                logger.warning("Embedding model unavailable (%s); using the built-in hashing embedder. "
                               "Semantic search will be weaker until the model can be downloaded.",
                               type(exc).__name__)
        if embedder is None:
            embedder = HashingEmbedder()
        _cached[backend] = embedder
        return embedder


def embed_texts(texts: list[str]) -> tuple[np.ndarray, str]:
    embedder = get_embedder()
    return embedder.embed(texts), embedder.name


def to_bytes(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_bytes(data) -> np.ndarray:
    return np.frombuffer(bytes(data), dtype=np.float32)
