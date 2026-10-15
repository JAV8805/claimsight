# ADR-0002: Use PostgreSQL + pgvector as the vector store

- Status: Accepted
- Date: 2026-10-15

## Context
ClaimSight needs to store claims (relational data), policy chunks with metadata,
embeddings for semantic search, and agent checkpoints. Retrieval must filter by
policy_id and effective_date before ranking by similarity.

## Decision
Use a single PostgreSQL 17 instance with the pgvector extension (0.8.x),
run locally through Docker Compose (`pgvector/pgvector:pg17` image).

## Alternatives considered
- Pinecone: managed and scalable, but adds a paid external dependency and splits
  data across two systems; metadata joins with claims would happen in application code.
- Qdrant / Weaviate: strong vector features, but one more service to run and secure.
- Chroma: simple for prototypes, weaker for relational joins and production use.

## Consequences
- One database for relational data, vectors and checkpoints: fewer moving parts, ACID joins,
  metadata filters in SQL.
- Hybrid search is possible with Postgres full-text search next to vector search.
- At very large scale a dedicated vector database may perform better; a benchmark against
  Qdrant or Pinecone will be documented as a comparison, not a dependency.
- Local ports are bound to 127.0.0.1 only (least exposure).
