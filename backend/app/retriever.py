"""Curriculum-aware hybrid retrieval — NCDC syllabus + UNEB past papers.

Forked from URA Chatbot retriever, retailored for A-Level STEM education.

Architecture:
- Dense: BAAI/bge-m3 (1024-dim, multilingual — handles Luganda)
- Sparse: BM25-weighted token vectors
- Fusion: RRF via Qdrant query API
- Reranking: mxbai-rerank-base-v2 cross-encoder
- Grounding: passage-level faithfulness scoring

Curriculum-aware features:
- Subject filtering (physics, chemistry, biology, mathematics)
- Syllabus section metadata preserved in passage payloads
- UNEB paper year and question number in citations
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "magezi_curriculum")
DENSE_MODEL_NAME = os.getenv("DENSE_MODEL", "BAAI/bge-m3")
RERANKER_MODEL_NAME = os.getenv("RERANKER_MODEL", "mixedbread-ai/mxbai-rerank-base-v2")
DENSE_DIM = int(os.getenv("DENSE_DIM", "1024"))
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() == "true"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
BM25_STATE_PATH = Path(
    os.getenv("BM25_STATE_PATH", str(_PROJECT_ROOT / "knowledge-base" / "bm25_state.json"))
)


# ---------------------------------------------------------------------------
# Circuit breaker (lightweight inline version)
# ---------------------------------------------------------------------------
from .resilience import CircuitBreaker


# ---------------------------------------------------------------------------
# BM25 sparse encoder
# ---------------------------------------------------------------------------
class BM25SparseEncoder:
    """BM25-weighted sparse vectors for Qdrant's inverted index."""

    def __init__(self) -> None:
        self._vocab: dict[str, int] = {}
        self._idf: dict[int, float] = {}
        self._next_id: int = 0
        self._k1: float = 1.2
        self._b: float = 0.75
        self._avg_dl: float = 0.0

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    def fit(self, documents: list[str]) -> BM25SparseEncoder:
        """Build vocabulary and IDF weights from documents."""
        n_docs = len(documents)
        doc_freq: Counter[int] = Counter()
        total_len = 0

        for doc in documents:
            tokens = self._tokenize(doc)
            total_len += len(tokens)
            seen: set[int] = set()
            for tok in tokens:
                if tok not in self._vocab:
                    self._vocab[tok] = self._next_id
                    self._next_id += 1
                tid = self._vocab[tok]
                if tid not in seen:
                    doc_freq[tid] += 1
                    seen.add(tid)

        self._avg_dl = total_len / max(n_docs, 1)
        for tid, df in doc_freq.items():
            self._idf[tid] = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)

        logger.info("BM25 encoder fit: vocab=%d docs=%d", len(self._vocab), n_docs)
        return self

    def encode(self, text: str) -> tuple[list[int], list[float]]:
        """Return (indices, values) for a Qdrant SparseVector."""
        tokens = self._tokenize(text)
        tf: Counter[str] = Counter(tokens)
        dl = len(tokens)

        indices: list[int] = []
        values: list[float] = []

        for tok, count in tf.items():
            tid = self._vocab.get(tok)
            if tid is None:
                continue
            idf = self._idf.get(tid, 0.0)
            num = count * (self._k1 + 1)
            denom = count + self._k1 * (1 - self._b + self._b * dl / max(self._avg_dl, 1))
            score = idf * num / denom
            if score > 0:
                indices.append(tid)
                values.append(round(score, 6))

        return indices, values

    def to_dict(self) -> dict[str, Any]:
        return {
            "vocab": self._vocab,
            "idf": {str(k): v for k, v in self._idf.items()},
            "avg_dl": self._avg_dl,
            "next_id": self._next_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BM25SparseEncoder:
        enc = cls()
        enc._vocab = data["vocab"]
        enc._idf = {int(k): v for k, v in data["idf"].items()}
        enc._avg_dl = data.get("avg_dl", 0.0)
        enc._next_id = data.get("next_id", 0)
        return enc


# ---------------------------------------------------------------------------
# Hybrid retriever with curriculum awareness
# ---------------------------------------------------------------------------
class HybridRetriever:
    """Curriculum-aware hybrid retriever: dense + sparse RRF + cross-encoder.

    Adds subject filtering and syllabus metadata to the base retriever.
    """

    def __init__(self) -> None:
        self._client: Any = None
        self._dense_model: Any = None
        self._reranker: Any = None
        self._sparse_encoder = BM25SparseEncoder()
        self._ready = False
        self._circuit = CircuitBreaker(
            name="qdrant",
            failure_threshold=3,
            reset_timeout=10.0,
            max_timeout=300.0,
        )
        # CPU-only: cache query embeddings — same students ask same things across turns.
        self._query_embed_cache: dict[str, list[float]] = {}
        self._query_embed_cache_max = 1024

    def initialize(self) -> bool:
        """Connect to Qdrant and load models."""
        # Always load BM25 first — works without Qdrant for keyword fallback
        if BM25_STATE_PATH.exists():
            try:
                with open(BM25_STATE_PATH) as f:
                    self._sparse_encoder = BM25SparseEncoder.from_dict(json.load(f))
                logger.info("Loaded BM25 state from %s", BM25_STATE_PATH)
            except Exception as e:
                logger.warning("BM25 load failed: %s", e)

        try:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(url=QDRANT_URL, timeout=10)
            collections = [c.name for c in self._client.get_collections().collections]
            if QDRANT_COLLECTION not in collections:
                logger.warning("Collection '%s' not found — retrieval unavailable", QDRANT_COLLECTION)
                return False

            from sentence_transformers import CrossEncoder, SentenceTransformer

            # CPU-only deployment: pin device explicitly so torch doesn't probe
            # for CUDA / spend startup time on a device that isn't there.
            self._dense_model = SentenceTransformer(DENSE_MODEL_NAME, device="cpu")
            if RERANK_ENABLED:
                self._reranker = CrossEncoder(RERANKER_MODEL_NAME, device="cpu")

            self._ready = True
            logger.info(
                "HybridRetriever ready (url=%s collection=%s rerank=%s)",
                QDRANT_URL, QDRANT_COLLECTION, RERANK_ENABLED,
            )
            return True
        except Exception:
            logger.warning("HybridRetriever init failed", exc_info=True)
            self._ready = False
            return False

    @property
    def is_ready(self) -> bool:
        """Check if retriever was initialised. Circuit breaker handles transient failures."""
        return self._ready and self._client is not None

    def search(
        self,
        query: str,
        top_k: int = 4,
        prefetch_limit: int = 20,
        subject: str | None = None,
    ) -> list[dict[str, Any]]:
        """Hybrid search with optional subject filtering.

        When subject is provided (e.g., "physics"), results are filtered
        to only return content tagged with that subject.
        """
        if not self._ready or self._client is None or self._dense_model is None:
            return []

        if not self._circuit.allow_request():
            logger.warning("Circuit breaker OPEN — skipping search")
            return []

        try:
            from qdrant_client import models

            cached = self._query_embed_cache.get(query)
            if cached is not None:
                dense_vec = cached
            else:
                dense_vec = self._dense_model.encode(query).tolist()
                if len(self._query_embed_cache) >= self._query_embed_cache_max:
                    self._query_embed_cache.pop(next(iter(self._query_embed_cache)))
                self._query_embed_cache[query] = dense_vec
            sparse_idx, sparse_val = self._sparse_encoder.encode(query)

            # Subject filter
            query_filter = None
            if subject:
                query_filter = models.Filter(
                    must=[
                        models.FieldCondition(
                            key="subject",
                            match=models.MatchValue(value=subject),
                        )
                    ]
                )

            prefetch = [
                models.Prefetch(query=dense_vec, using="dense", limit=prefetch_limit),
            ]
            if sparse_idx:
                prefetch.append(
                    models.Prefetch(
                        query=models.SparseVector(indices=sparse_idx, values=sparse_val),
                        using="sparse",
                        limit=prefetch_limit,
                    )
                )

            results = self._client.query_points(
                collection_name=QDRANT_COLLECTION,
                prefetch=prefetch,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                query_filter=query_filter,
                limit=prefetch_limit,
            )

            if not results.points:
                self._circuit.record_success()
                return []

            candidates: list[dict[str, Any]] = []
            for pt in results.points:
                p = pt.payload or {}
                candidates.append({
                    "id": str(pt.id),
                    "text": p.get("text", ""),
                    "question": p.get("question", ""),
                    "answer": p.get("answer", ""),
                    "source": p.get("source", ""),
                    "chunk_id": p.get("chunk_id", ""),
                    "page": p.get("page", ""),
                    "section": p.get("section", ""),
                    "subject": p.get("subject", ""),
                    "topic": p.get("topic", ""),
                    "year": p.get("year", ""),
                    "paper": p.get("paper", ""),
                    "doc_type": p.get("doc_type", ""),
                    "score_rrf": float(pt.score) if pt.score else 0.0,
                })

            # Cross-encoder reranking
            if self._reranker and candidates:
                pairs = [
                    (query, c.get("text") or c.get("answer") or c.get("question", ""))
                    for c in candidates
                ]
                scores = self._reranker.predict(pairs)
                for i, s in enumerate(scores):
                    candidates[i]["score_rerank"] = float(s)
                candidates.sort(key=lambda x: x.get("score_rerank", 0.0), reverse=True)

            self._circuit.record_success()
            return candidates[:top_k]

        except Exception:
            self._circuit.record_failure()
            logger.exception("Hybrid search failed")
            return []

    @staticmethod
    def compute_faithfulness(answer: str, contexts: list[str]) -> float:
        """Fraction of answer sentences grounded in the retrieved contexts."""
        if not answer or not contexts:
            return 0.0

        sentences = [s.strip() for s in re.split(r"[.!?]+", answer) if len(s.strip()) > 5]
        if not sentences:
            return 1.0

        ctx_tokens = set(re.findall(r"\w+", " ".join(contexts).lower()))
        grounded = 0
        for sent in sentences:
            sent_tokens = set(re.findall(r"\w+", sent.lower()))
            if not sent_tokens:
                continue
            if len(sent_tokens & ctx_tokens) / len(sent_tokens) >= 0.5:
                grounded += 1

        return round(grounded / len(sentences), 4)

    @staticmethod
    def build_citations(hits: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Build curriculum-aware citations from retrieval hits."""
        citations: list[dict[str, str]] = []
        for i, hit in enumerate(hits, 1):
            cit: dict[str, str] = {
                "ref": f"[{i}]",
                "source": hit.get("source", "unknown"),
            }
            if hit.get("page"):
                cit["page"] = str(hit["page"])
            if hit.get("section"):
                cit["section"] = str(hit["section"])
            if hit.get("subject"):
                cit["subject"] = str(hit["subject"])
            if hit.get("topic"):
                cit["topic"] = str(hit["topic"])
            if hit.get("year"):
                cit["year"] = str(hit["year"])
            if hit.get("paper"):
                cit["paper"] = str(hit["paper"])
            passage = hit.get("text") or hit.get("answer") or ""
            cit["passage"] = passage[:500]
            citations.append(cit)
        return citations
