"""Typed per-dimension embedding columns (M54, scale-B5, spec §16.1).

The side-table used to hold an untyped `vector`, which pgvector cannot
index: every cosine leg was a sequential scan, and recall latency grew with
the corpus. Now the vector lives in one typed column per supported
dimension, each with a real HNSW cosine index; the column is chosen from
the model key's dims (`provider:model@dims`), so several dimensions coexist
— the provider-agnostic, zero-downtime model switch §16.1 promised — and
each is indexable. Dimensions above pgvector's 2000-dim index ceiling use
`halfvec` (16-bit components), the type pgvector indexes up to 4000.
"""

from __future__ import annotations

# the supported set and the halfvec threshold are declared beside the
# columns they describe (app/models/memory.py — a leaf module; this package
# imports the store and would cycle the other way round)
from app.models.memory import EMBEDDING_DIMS, HALFVEC_ABOVE

__all__ = [
    "EMBEDDING_DIMS",
    "HALFVEC_ABOVE",
    "dims_of",
    "embedding_column",
    "vector_column",
    "vector_type",
]


def embedding_column(dims: int) -> str | None:
    """The column that stores vectors of `dims`, or None when unsupported."""
    return f"emb_{dims}" if dims in EMBEDDING_DIMS else None


def vector_type(dims: int) -> str:
    """The SQL type of that column — what a query parameter is CAST to."""
    return "halfvec" if dims > HALFVEC_ABOVE else "vector"


def dims_of(model_key: str | None) -> int | None:
    """`provider:model@dims` → dims."""
    if not model_key or "@" not in model_key:
        return None
    tail = model_key.rsplit("@", 1)[1]
    return int(tail) if tail.isdigit() else None


def vector_column(model_key: str | None) -> tuple[str, str] | None:
    """(column, cast type) for a model key, or None when its dimension has
    no column — that row is lexical-only."""
    dims = dims_of(model_key)
    if dims is None:
        return None
    column = embedding_column(dims)
    return (column, vector_type(dims)) if column else None
