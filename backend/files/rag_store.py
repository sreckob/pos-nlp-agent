"""
rag_store.py — pgvector retrieval for dispute regulation clauses
================================================================
Retrieves the most relevant chargeback regulation clauses given a
dispute scenario description. Used by approval_agent.py to enrich
audit summaries with regulatory citations.

The sentence-transformers model is loaded lazily on first call so it
does not slow FastAPI startup. If the dispute_policies table does not
exist (i.e. ingest_policies.py has not been run), retrieve_clauses()
returns an empty list and the approver falls back to its normal behaviour.
"""

import logging
from typing import Any, Dict, List

from db import get_conn

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("RAG: sentence-transformers model loaded (all-MiniLM-L6-v2)")
    return _model


def embed(text: str) -> List[float]:
    return _get_model().encode(text, normalize_embeddings=True).tolist()


def retrieve_clauses(scenario: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Return top_k regulation clauses most similar to the dispute scenario.
    Returns empty list on any error so the approver degrades gracefully.
    """
    try:
        vec = embed(scenario)
        vec_literal = "[" + ",".join(f"{x:.8f}" for x in vec) + "]"
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT source, clause_id, content,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM dispute_policies
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (vec_literal, vec_literal, top_k),
                )
                rows = cur.fetchall()
        return [
            {
                "source":     row[0],
                "clause_id":  row[1],
                "content":    row[2],
                "similarity": round(float(row[3]), 3),
            }
            for row in rows
        ]
    except Exception as exc:
        logger.warning(f"RAG retrieval skipped (table missing or error): {exc}")
        return []
