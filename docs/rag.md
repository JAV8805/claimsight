# Retrieval over the policy (L2.2a)

Coverage decisions must cite policy clauses (FR-13). This document explains how the policy is stored and searched, and how we measure the search before any model writes an answer.

The corpus is the fictional **ClaimSight Mutual Auto Policy** (`corpus/policies/`, English and Spanish, 28 clauses with stable IDs such as `CS-AUTO-4.2`, same IDs in both languages). It is synthetic: amounts and time limits are invented.

## Chunking

An embedding model turns a piece of text into one vector, so the text must be cut into pieces before indexing. The cut decides what a search result *is*.

| Chunker | What a chunk is | Strength | Weakness |
| --- | --- | --- | --- |
| `clause` | One whole clause | A result is directly a citable ID; one idea per vector | Clauses differ in length |
| `fixed` | 400 characters, 80 shared with the previous chunk | Simple, ignores document structure | A chunk can mix two clauses or cut one in half; overlap only softens that |

Each fixed chunk is assigned its **primary clause** (the clause contributing most of its characters) and also stores every clause it touches in `metadata.clause_ids`. Scoring uses the primary clause only, which is conservative for `fixed`. Every chunk stores `clause_id`, `language` and `section` as columns.

Each chunker has its own table (`policy_chunks_clause`, `policy_chunks_fixed`), rebuilt on every ingest.

## Embeddings

`bge-m3` (Ollama, 1024 dimensions) is multilingual: sentences with the same meaning in English and Spanish land close together in the same vector space. That is what makes cross-lingual search (a Spanish narrative against English clauses) possible at all. It runs locally, so retrieval costs nothing.

## HNSW and cosine distance

- **Cosine distance** (`<=>` in pgvector) compares the *direction* of two vectors and ignores their length, which is the usual choice for text embeddings. The index operator class must match the query operator: `vector_cosine_ops` with `<=>`.
- **HNSW** (Hierarchical Navigable Small World) is an approximate nearest-neighbour index: a layered graph where each vector links to near neighbours, and a search walks from the top sparse layer down to the dense bottom layer. It trades a little recall for speed. `m = 16` is the links per node and `ef_construction = 64` the candidates considered while building; `hnsw.ef_search = 200` is how many candidates a query keeps. With 56 clause chunks this is far more than the corpus, so results are effectively exact; the settings matter when the corpus grows. `ef_search` also has to be large enough for the language filter: the filter is applied after the index returns candidates.

## Why recall is measured before generation

If the clause that answers the question is not retrieved, no generator can cite it; it will either miss it or invent something plausible. Measuring retrieval alone isolates that failure and is cheap, deterministic and free of LLM judgment. Only after retrieval is good enough does it make sense to measure the generated coverage decision, and then a wrong answer can be traced to retrieval or to generation.

Metrics, computed per case against the expected clauses:
- **recall@k**: the share of the expected clauses present in the top k results (k = 3 and 5).
- **MRR**: 1 divided by the rank of the first expected clause; it says how early the first useful clause appears.

Settings: *monolingual* (query and clauses in the same language) and *cross-lingual* (the other language). Query = the case narrative, as written.

Run with `make eval-retrieval` (needs `make up` and Ollama with `bge-m3`); the report is `evals/reports/retrieval.json`. The unit tests cover chunkers, metrics and the corpus without Ollama or a database, so CI stays offline.

## Known limitations

- **The expected clauses are proposals.** `evals/golden/clause_proposals.json` is pending José's review; scores will move when labels change.
- **Narratives do not mention deductibles, VIN checks or police reports.** A query built from the narrative alone cannot be expected to retrieve `CS-AUTO-5.x`, `7.1` or `6.3`; these account for most misses (see the validation log). Retrieval for those needs the claim type or signals in the query (query expansion) or deterministic lookup, which is a next step.
- **Small synthetic corpus.** 28 clauses per language: scores say little about a real policy of hundreds of pages, where chunk size and index settings matter far more.
