"""
Turn raw job postings into structured records.

This is the rule-based baseline for Component 1 (Knowledge Engine). It is meant
to be replaced/compared against the fine-tuned DistilBERT extractor and the
GPT-4o prompt baseline, so it keeps the same output shape those will produce.

Improvements over the first version:
  * postings are split into sections (about / responsibilities / required /
    preferred) so skills can be marked required vs preferred
  * responsibilities come from the responsibilities section instead of any
    line containing "build" or "design" (which pulled in company marketing copy)
  * skill detection uses the shared taxonomy in backend/skills.py
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .skills import find_skills

MAX_LINE_CHARS = 350  # longer lines are almost always company blurbs, not requirements

_HEADER_KINDS = [
    ("preferred", r"preferred|nice to have|bonus|plus|good to have|extra credit|even better|skills you.?ll build|desired"),
    ("required", r"qualifications?|requirements?|what you.?ll need|what you bring|what we.?re looking for|what we are looking for|who you are|you have|you.?ll bring|minimum|must have|about you|basic|ideal for this role|you are ideal|if you.?re|if you are"),
    ("responsibilities", r"responsibilit|what you.?ll do|what you will do|the role|your impact|in this role|day to day|you will|you.?ll be|role overview|job description"),
    ("about", r"about (us|the company|the team)|who we are|our (mission|team|culture)|why join|benefits|perks|compensation|salary|equal opportunity|how we work|what we offer"),
]
_HEADER_RES = [(kind, re.compile(rf"\b(?:{pattern})", re.IGNORECASE)) for kind, pattern in _HEADER_KINDS]

_DEGREE_RE = re.compile(
    r"bachelor|master|degree|ph\.?d|computer science|coursework|currently (enrolled|pursuing)|undergraduate|graduate",
    re.IGNORECASE,
)
_EXPERIENCE_RE = re.compile(r"\byears?\b|experience|internship|co-?op|hands-on|familiar", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*(?:[-•*–]|\d+[.)])\s+")
_BARE_BULLET_RE = re.compile(r"^\s*[-•*–]\s*$")


def read_jsonl(file_path: str) -> list[dict]:
    """Read one JSON object per line, skipping malformed lines."""
    postings = []
    with open(file_path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                postings.append(json.loads(line))
            except json.JSONDecodeError as error:
                print(f"Skipping invalid line {line_number}: {error}")
    return postings


def write_jsonl(records: list[dict], file_path: str) -> None:
    output_path = Path(file_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def _heading_kind(line: str) -> str | None:
    """Classify a short line as a section heading, or None if it is body text."""
    stripped = line.strip().strip("*#:").strip()
    if not stripped or len(stripped) > 70 or _BULLET_RE.match(line):
        return None
    # Headings rarely end with a period and are not full sentences.
    if stripped.endswith(".") or len(stripped.split()) > 9:
        return None
    for kind, regex in _HEADER_RES:
        if regex.search(stripped):
            return kind
    return None


def split_posting_sections(text: str) -> dict[str, list[str]]:
    """Group posting lines into about / responsibilities / required / preferred / other."""
    sections: dict[str, list[str]] = {
        "about": [], "responsibilities": [], "required": [], "preferred": [], "other": [],
    }
    current = "about"
    for raw_line in text.splitlines():
        line = raw_line.strip()
        # Skip blanks and bare bullet markers ("-" alone on a line is common in scraped text).
        if not line or _BARE_BULLET_RE.match(line):
            continue
        kind = _heading_kind(line)
        if kind:
            current = kind
            continue
        sections[current].append(_BULLET_RE.sub("", line).strip())
    return sections


def _short(lines: list[str]) -> list[str]:
    return [line for line in lines if 0 < len(line) <= MAX_LINE_CHARS]


def extract_skills(text: str) -> list[str]:
    """All known skills mentioned anywhere in `text` (kept for backwards compatibility)."""
    return find_skills(text)


def parse_posting(posting: dict) -> dict:
    """Convert one raw posting into a structured record."""
    text = posting.get("text", "") or ""
    sections = split_posting_sections(text)

    required_text = "\n".join(sections["required"] + sections["responsibilities"])
    preferred_text = "\n".join(sections["preferred"])

    preferred_skills = find_skills(preferred_text)
    required_skills = [s for s in find_skills(required_text) if s not in preferred_skills]
    # Skills that only appear in "about" or unlabeled text still count, as required.
    leftover = find_skills("\n".join(sections["about"] + sections["other"]))
    required_skills = sorted(set(required_skills) | {s for s in leftover if s not in preferred_skills})

    qualification_lines = _short(sections["required"] + sections["preferred"])
    responsibilities = _short(sections["responsibilities"])

    # Fall back to scanning all lines if the posting had no recognisable headings.
    all_lines = _short([
        _BULLET_RE.sub("", l).strip() for l in text.splitlines()
        if l.strip() and not _BARE_BULLET_RE.match(l)
    ])
    if not qualification_lines:
        qualification_lines = [l for l in all_lines if _EXPERIENCE_RE.search(l)][:12]
    if not responsibilities:
        responsibilities = [
            l for l in all_lines
            if re.match(r"^(build|develop|design|implement|write|test|debug|maintain|analyze|work|collaborate|contribute|create|help)\b", l, re.IGNORECASE)
        ][:12]

    return {
        "id": posting.get("id", ""),
        "company": posting.get("company", ""),
        "title": posting.get("title", ""),
        "location": posting.get("location", ""),
        "url": posting.get("url", ""),
        "skills_mentioned": sorted(set(required_skills) | set(preferred_skills)),
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "responsibilities": responsibilities,
        "qualification_lines": qualification_lines,
        "education_lines": [l for l in all_lines if _DEGREE_RE.search(l)][:6],
        "experience_lines": [l for l in qualification_lines if _EXPERIENCE_RE.search(l)][:8],
    }


def main():
    parser = argparse.ArgumentParser(description="Parse collected internship postings.")
    parser.add_argument("--input", default="data/raw_postings.jsonl", help="Input JSONL file")
    parser.add_argument("--output", default="data/parsed_postings.jsonl", help="Output JSONL file")
    parser.add_argument("--limit", type=int, default=0, help="Max postings to process; 0 means all")
    args = parser.parse_args()

    postings = read_jsonl(args.input)
    if args.limit > 0:
        postings = postings[: args.limit]

    write_jsonl([parse_posting(p) for p in postings], args.output)
    print(f"Read {len(postings)} postings.")
    print(f"Wrote parsed results to {args.output}")


if __name__ == "__main__":
    main()
