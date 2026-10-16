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

## Why hybrid: not every citation is retrievable

The first version searched the whole policy with the narrative. It reached only about half of the clauses a coverage decision must cite, because many citations have nothing to do with the words of the narrative. A claimant describing hail never mentions a deductible, a police report or the VIN check, yet the decision must cite those clauses. Search cannot find what the query does not say.

So citations are split by how they are found:

| Clauses | How | Why |
| --- | --- | --- |
| Deductibles (5.x), police report (6.3), VIN and information clauses (1.1, 6.4, 7.1, 7.2) | **Deterministic clause map** (`claimsight.rag.clause_map`) from the claim type and the signals | They follow from rules, so looking them up is exact and free |
| Coverage and exclusions (sections 2 to 4) | **Semantic retrieval**, query = claim type + narrative, limited to those sections | They depend on what happened, which only the text says |

**Proportionality rule for 7.1 (accurate information).** The clause is cited only when what the *insured* said is inconsistent: VIN mismatch, malformed VIN, or a narrative that contradicts the claimed event. A weather mismatch alone does not cite it, because weather comes from an external source and is not information the insured gave.

## Why recall is measured before generation

If the clause that answers the question is not retrieved, no generator can cite it; it will either miss it or invent something plausible. Measuring retrieval alone isolates that failure and is cheap, deterministic and free of LLM judgment. Only after retrieval is good enough does it make sense to measure the generated coverage decision, and then a wrong answer can be traced to retrieval or to generation.

Metrics, computed per case against the decided `expected.clause_ids` of `labels.json`:
- **recall@k**: the share of the expected clauses present in the top k results (k = 3 and 5).
- **MRR**: 1 divided by the rank of the first expected clause; it says how early the first useful clause appears.

The report has four parts per chunker and setting:
- `pure_semantic`: the previous method (narrative only, whole policy, all expected clauses), kept for comparison.
- `semantic`: the semantic part of the hybrid, scored against the expected clauses of sections 2 to 4 only (recall@3, recall@5, MRR).
- `combined`: end-to-end recall of the clause map plus the top k semantic results against all expected clauses.
- `deterministic`: exact-match rate of the clause map against the expected clauses outside sections 2 to 4.

Settings: *monolingual* (query and clauses in the same language) and *cross-lingual* (the other language). The clause map does not depend on language.

**The classifier is not in this loop.** The eval uses `claimed_event` as the claim type, and the map's signals come from the rules baseline. So the cases that need language understanding are expected to miss in the deterministic part: GC-0009 and GC-0053 (narrative contradicts the claimed event: wrong deductible and no 7.1) and GC-0012 (prompt injection: no 7.2). The next step is to feed the LLM triage prediction instead.

Run with `make eval-retrieval` (needs `make up` and Ollama with `bge-m3`); the report is `evals/reports/retrieval.json`. The unit tests cover chunkers, metrics, the clause map and the decided labels without Ollama or a database, so CI stays offline.

## Known limitations

- **Labels are decided but small.** `expected.clause_ids` was decided by José for the 60 synthetic cases; the scores say how well the system reproduces those decisions.
- **Query effects are not separated.** The `semantic` part changes three things against `pure_semantic` at once (claim type in the query, section filter, scoring only sections 2 to 4), so its gain is not attributable to one of them. `combined` against `pure_semantic` is the like-for-like end-to-end comparison.
- **Small synthetic corpus.** 28 clauses per language: scores say little about a real policy of hundreds of pages, where chunk size and index settings matter far more.
