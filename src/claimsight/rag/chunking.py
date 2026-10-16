"""Policy parsing and the two chunking strategies compared in L2.2a.

Pure functions, no database and no model, so they are unit-tested offline.

- clause-based: one chunk per clause. The unit of meaning is the unit of citation, so a
  retrieved chunk is directly a citable clause ID (FR-13).
- fixed-size with overlap: the body text cut every `size - overlap` characters, ignoring the
  document structure. The usual baseline. A chunk is assigned the clause that contributes the
  most characters to it (its primary clause) and also lists every clause it touches.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

CLAUSE_HEADING = re.compile(r"^### (CS-AUTO-\d+\.\d+) (.+)$", re.M)
SECTION_HEADING = re.compile(r"^## (\d+)\. (.+)$", re.M)
FIXED_SIZE = 400
FIXED_OVERLAP = 80


@dataclass(frozen=True)
class Clause:
    clause_id: str
    language: str
    section: str
    title: str
    text: str  # heading line plus body


@dataclass(frozen=True)
class Chunk:
    text: str
    clause_id: str  # primary clause
    language: str
    section: str
    clause_ids: tuple[str, ...] = field(default=())  # every clause the chunk overlaps


def parse_policy(markdown: str, language: str) -> list[Clause]:
    """Split a policy Markdown file into clauses; the header and section titles are metadata."""
    sections = [
        (m.start(), f"{m.group(1)}. {m.group(2)}") for m in SECTION_HEADING.finditer(markdown)
    ]
    matches = list(CLAUSE_HEADING.finditer(markdown))
    clauses = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        body = markdown[m.start() : end]
        # drop the next section heading that trails the last clause of a section
        body = SECTION_HEADING.split(body)[0] if SECTION_HEADING.search(body) else body
        section = next((name for pos, name in reversed(sections) if pos < m.start()), "")
        clauses.append(Clause(m.group(1), language, section, m.group(2), body.strip()))
    return clauses


def load_policy(path: Path) -> list[Clause]:
    language = path.name.split(".")[-2]  # claimsight-mutual-auto-policy.<lang>.md
    return parse_policy(path.read_text(encoding="utf-8"), language)


def chunk_by_clause(clauses: list[Clause]) -> list[Chunk]:
    return [Chunk(c.text, c.clause_id, c.language, c.section, (c.clause_id,)) for c in clauses]


def chunk_fixed(
    clauses: list[Clause], size: int = FIXED_SIZE, overlap: int = FIXED_OVERLAP
) -> list[Chunk]:
    """Cut the concatenated clause text into windows of `size` characters, `overlap` shared."""
    if not 0 <= overlap < size:
        raise ValueError("overlap must be >= 0 and smaller than size")
    if not clauses:
        return []
    text, spans = "", []  # span: (start, end, clause)
    for clause in clauses:
        spans.append((len(text), len(text) + len(clause.text), clause))
        text += clause.text + "\n\n"
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        piece = text[start:end].strip()
        if piece:
            share = [(min(end, e) - max(start, s), c) for s, e, c in spans if s < end and e > start]
            share = [(n, c) for n, c in share if n > 0]
            primary = max(share, key=lambda item: item[0])[1]
            ids = tuple(c.clause_id for _, c in share)
            chunks.append(Chunk(piece, primary.clause_id, primary.language, primary.section, ids))
        if end == len(text):
            break
        start = end - overlap
    return chunks


CHUNKERS = {"clause": chunk_by_clause, "fixed": chunk_fixed}
