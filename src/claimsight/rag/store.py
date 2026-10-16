"""pgvector store: one table per chunking strategy, HNSW index with cosine distance.

Embeddings come from Ollama bge-m3 (1024 dimensions, multilingual). `<=>` is pgvector's cosine
distance, so the index uses `vector_cosine_ops` and queries order by `embedding <=> query`.
"""

import os
from collections.abc import Sequence
from pathlib import Path

import psycopg
from langchain_ollama import OllamaEmbeddings
from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb

from claimsight.rag.chunking import CHUNKERS, Chunk, load_policy

EMBED_MODEL = "bge-m3"
EMBED_DIM = 1024
POLICY_DIR = Path("corpus/policies")
HNSW_M = 16
HNSW_EF_CONSTRUCTION = 64
EF_SEARCH = 200  # candidates kept per query; above the corpus size, so the language filter is exact


def table_name(chunker: str) -> str:
    if chunker not in CHUNKERS:  # the name goes into SQL: only known strategies are allowed
        raise ValueError(f"unknown chunker {chunker!r}")
    return f"policy_chunks_{chunker}"


def connect() -> psycopg.Connection:
    conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


def embedder() -> OllamaEmbeddings:
    return OllamaEmbeddings(model=EMBED_MODEL)


def ingest(conn: psycopg.Connection, chunker: str, embeddings: OllamaEmbeddings) -> int:
    """Rebuild the collection of one chunker from the policy files; returns the chunk count."""
    table = table_name(chunker)
    chunks: list[Chunk] = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        chunks += CHUNKERS[chunker](load_policy(path))
    vectors = embeddings.embed_documents([c.text for c in chunks])
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute(
        f"""CREATE TABLE {table} (
            id serial PRIMARY KEY,
            clause_id text NOT NULL,
            language text NOT NULL,
            section text NOT NULL,
            metadata jsonb NOT NULL,
            content text NOT NULL,
            embedding vector({EMBED_DIM}) NOT NULL)"""
    )
    with conn.cursor() as cur:
        cur.executemany(
            f"INSERT INTO {table} (clause_id, language, section, metadata, content, embedding) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            [
                (
                    c.clause_id,
                    c.language,
                    c.section,
                    Jsonb({"clause_ids": list(c.clause_ids)}),
                    c.text,
                    v,
                )
                for c, v in zip(chunks, vectors, strict=True)
            ],
        )
    conn.execute(
        f"CREATE INDEX ON {table} USING hnsw (embedding vector_cosine_ops) "
        f"WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION})"
    )
    return len(chunks)


def search(
    conn: psycopg.Connection,
    chunker: str,
    vector: Sequence[float],
    language: str,
    k: int,
    sections: Sequence[str] | None = None,
) -> list[str]:
    """Clause IDs of the k nearest chunks of one language, nearest first.

    `sections` (e.g. ["2", "3", "4"]) keeps only chunks whose primary clause is in those
    policy sections; the section column starts with the section number ("3. Comprehensive").
    """
    conn.execute(f"SET hnsw.ef_search = {EF_SEARCH}")
    where, params = "language = %s", [language]
    if sections:
        where += " AND split_part(section, '.', 1) = ANY(%s)"
        params.append(list(sections))
    rows = conn.execute(
        f"SELECT clause_id FROM {table_name(chunker)} WHERE {where} "
        "ORDER BY embedding <=> %s::vector LIMIT %s",
        (*params, list(vector), k),
    ).fetchall()
    return [r[0] for r in rows]
