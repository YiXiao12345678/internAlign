"""In-memory access to parsed postings (loaded once, reloaded if the file changes)."""
from __future__ import annotations

from . import config
from .job_parser import read_jsonl

_cache: dict = {"mtime": None, "postings": []}


def load_postings() -> list[dict]:
    path = config.POSTINGS_PATH
    if not path.exists():
        return []
    mtime = path.stat().st_mtime
    if _cache["mtime"] != mtime:
        _cache["postings"] = read_jsonl(str(path))
        _cache["mtime"] = mtime
    return _cache["postings"]


def get_posting(posting_id: str) -> dict | None:
    return next((p for p in load_postings() if p.get("id") == posting_id), None)


def posting_summary(posting: dict) -> dict:
    """Lightweight shape for list views."""
    return {
        "id": posting.get("id", ""),
        "company": posting.get("company", ""),
        "title": posting.get("title", ""),
        "location": posting.get("location", ""),
        "url": posting.get("url", ""),
        "required_skills": posting.get("required_skills", posting.get("skills_mentioned", [])),
        "preferred_skills": posting.get("preferred_skills", []),
    }
