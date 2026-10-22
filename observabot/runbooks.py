"""Keyword search over the markdown runbooks in a directory."""

import re
from dataclasses import dataclass
from pathlib import Path

MAX_EXCERPT_CHARS = 1500
MAX_RESULTS = 3
_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Runbook:
    slug: str
    title: str
    body: str


def load_runbooks(directory: str | Path) -> list[Runbook]:
    runbooks = []
    for path in sorted(Path(directory).glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        text = path.read_text(encoding="utf-8")
        title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), path.stem)
        runbooks.append(Runbook(slug=path.stem, title=title, body=text))
    return runbooks


def _terms(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def search_runbooks(runbooks: list[Runbook], query: str) -> list[Runbook]:
    """Rank runbooks by how many query terms appear, weighting title matches higher."""
    query_terms = _terms(query)
    if not query_terms:
        return []

    scored = []
    for runbook in runbooks:
        title_hits = len(query_terms & _terms(runbook.title))
        body_hits = len(query_terms & _terms(runbook.body))
        score = 3 * title_hits + body_hits
        if score > 0:
            scored.append((score, runbook))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [runbook for _, runbook in scored[:MAX_RESULTS]]


def excerpt(runbook: Runbook) -> str:
    if len(runbook.body) <= MAX_EXCERPT_CHARS:
        return runbook.body
    return runbook.body[:MAX_EXCERPT_CHARS].rstrip() + "\n...[truncated]"
