"""Semantic retrieval of policy clauses as a LangChain retriever."""

from typing import Any

import psycopg
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

from claimsight.rag import store

SEMANTIC_SECTIONS = ("2", "3", "4")  # coverage and exclusions; the rest comes from the clause map


class PolicyRetriever(BaseRetriever):
    """Top-k policy chunks of one language, nearest first, from the pgvector collection of a
    chunker. Each document carries `clause_id`, `language` and `section` as metadata."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    conn: psycopg.Connection[Any]
    embeddings: Embeddings
    language: str
    chunker: str = "clause"
    k: int = 5
    sections: tuple[str, ...] | None = SEMANTIC_SECTIONS

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        vector = self.embeddings.embed_query(query)
        rows = store.search_chunks(
            self.conn, self.chunker, vector, self.language, self.k, self.sections
        )
        return [
            Document(
                page_content=content,
                metadata={"clause_id": clause_id, "language": self.language, "section": section},
            )
            for clause_id, section, content in rows
        ]
