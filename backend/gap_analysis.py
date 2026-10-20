"""
Resume gap analysis (Component 2, rule-based baseline) and job ranking (Component 3).

For every skill a posting asks for, we decide whether the resume:
  * "Supported"           - mentions the skill directly
  * "Partially supported" - mentions a closely related skill (e.g. PyTorch for machine learning)
  * "Not found"           - has no evidence

Nothing is invented: evidence is always an exact line from the resume, and
every gap becomes a clarification question for the user. Only answers the
user confirms may later be used to rewrite the resume.

This is the baseline the GPT-4o + RAG pipeline will be compared against.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .job_parser import read_jsonl
from .resume_parser import extract_resume_text, split_sections
from .skills import SKILL_BY_NAME, label, mentions

SUPPORTED = "Supported"
PARTIAL = "Partially supported"
NOT_FOUND = "Not found"

# How much each requirement counts toward the score.
IMPORTANCE_WEIGHT = {"required": 1.0, "preferred": 0.5}
STATUS_CREDIT = {SUPPORTED: 1.0, PARTIAL: 0.5, NOT_FOUND: 0.0}

# Sections where a skill is merely listed vs. shown in use.
_LIST_SECTIONS = {"skills", "education", "header", "summary"}


def _resume_lines(resume_text: str) -> list[tuple[str, str]]:
    """(section, line) pairs for every non-empty resume line."""
    return [
        (section, line)
        for section, lines in split_sections(resume_text).items()
        for line in lines
    ]


def find_evidence(skill: str, resume_text: str, limit: int = 3) -> list[dict]:
    """Resume lines that mention `skill`, strongest evidence first."""
    hits = [
        {"line": line, "section": section}
        for section, line in _resume_lines(resume_text)
        if mentions(skill, line)
    ]
    # Lines from experience/projects show the skill in use, so list them first.
    hits.sort(key=lambda hit: hit["section"] in _LIST_SECTIONS)
    return hits[:limit]


def _evidence_type(evidence: list[dict]) -> str | None:
    if not evidence:
        return None
    return "listed" if all(h["section"] in _LIST_SECTIONS for h in evidence) else "demonstrated"


def _clarification(skill: str, status: str, evidence_type: str | None, related_found: str | None) -> dict | None:
    name = label(skill)
    if status == NOT_FOUND:
        return {
            "kind": "missing",
            "question": (
                f"The posting asks for {name}. Have you used {name}, or something similar, "
                "in a course, project, or job? If so, what did you build and what was your role?"
            ),
        }
    if status == PARTIAL:
        related = label(related_found) if related_found else "a related tool"
        return {
            "kind": "partial",
            "question": (
                f"Your resume mentions {related}, but not {name}. "
                f"Have you also worked with {name}? If so, where and how?"
            ),
        }
    if evidence_type == "listed":
        return {
            "kind": "strengthen",
            "question": (
                f"{name} appears in your skills list. Which project or role shows you using it, "
                "and what was the result?"
            ),
        }
    return None


def analyze_skill(skill: str, resume_text: str, importance: str = "required") -> dict:
    """Compare one posting skill against the resume."""
    evidence = find_evidence(skill, resume_text)
    related_found = None

    if evidence:
        status = SUPPORTED
    else:
        related = SKILL_BY_NAME[skill].related if skill in SKILL_BY_NAME else ()
        related_found = next((r for r in related if find_evidence(r, resume_text, limit=1)), None)
        if related_found:
            status = PARTIAL
            evidence = find_evidence(related_found, resume_text)
        else:
            status = NOT_FOUND

    evidence_type = _evidence_type(evidence) if status == SUPPORTED else None
    clarification = _clarification(skill, status, evidence_type, related_found)

    return {
        "requirement": skill,
        "display_name": label(skill),
        "importance": importance,
        "status": status,
        "evidence_type": evidence_type,
        "related_skill": related_found,
        "resume_evidence": [hit["line"] for hit in evidence],  # kept for backwards compatibility
        "evidence": evidence,
        "clarification": clarification,
    }


def _score(results: list[dict]) -> int | None:
    total = sum(IMPORTANCE_WEIGHT[r["importance"]] for r in results)
    if not total:
        return None
    earned = sum(IMPORTANCE_WEIGHT[r["importance"]] * STATUS_CREDIT[r["status"]] for r in results)
    return round(100 * earned / total)


def score_label(score: int | None) -> str:
    if score is None:
        return "Not enough detail"
    if score >= 85:
        return "Excellent match"
    if score >= 70:
        return "Strong match"
    if score >= 50:
        return "Partial match"
    return "Stretch"


def analyze_posting(posting: dict, resume_text: str) -> dict:
    required = posting.get("required_skills")
    preferred = posting.get("preferred_skills", [])
    if required is None:  # postings parsed by the first version of the parser
        required, preferred = posting.get("skills_mentioned", []), []

    results = [analyze_skill(s, resume_text, "required") for s in required]
    results += [analyze_skill(s, resume_text, "preferred") for s in preferred]
    # Biggest gaps first so the UI leads with what matters.
    order = {NOT_FOUND: 0, PARTIAL: 1, SUPPORTED: 2}
    results.sort(key=lambda r: (r["importance"] != "required", order[r["status"]], r["requirement"]))

    summary = {SUPPORTED: 0, PARTIAL: 0, NOT_FOUND: 0}
    for result in results:
        summary[result["status"]] += 1

    score = _score(results)
    return {
        "posting_id": posting.get("id", ""),
        "company": posting.get("company", ""),
        "title": posting.get("title", ""),
        "location": posting.get("location", ""),
        "job_url": posting.get("url", ""),
        "score": score,
        "score_label": score_label(score),
        "summary": summary,
        "requirements": results,
        "clarification_questions": [r["clarification"] | {"requirement": r["requirement"]} for r in results if r["clarification"]],
        "note": None if results else "No specific technical skills were detected in this posting, so a match score isn't available.",
    }


def rank_postings(postings: list[dict], resume_text: str) -> list[dict]:
    """Analyze every posting and order them from best to worst fit."""
    analyses = [analyze_posting(p, resume_text) for p in postings]
    # Postings without a score sort last.
    analyses.sort(key=lambda a: (a["score"] is None, -(a["score"] or 0), a["company"]))
    return analyses


def main():
    parser = argparse.ArgumentParser(description="Compare a resume with parsed job postings.")
    parser.add_argument("--resume", required=True, help="Path to the resume (PDF, DOCX or TXT)")
    parser.add_argument("--job", default="data/parsed_postings.jsonl", help="Parsed postings JSONL")
    parser.add_argument("--posting-index", type=int, default=0, help="Which posting to analyze; starts at 0")
    parser.add_argument("--rank", action="store_true", help="Rank all postings instead of analyzing one")
    parser.add_argument("--output", default="data/gap_analysis.json", help="Output JSON file")
    args = parser.parse_args()

    resume_text = extract_resume_text(args.resume)
    postings = read_jsonl(args.job)
    if not postings:
        raise ValueError("No parsed job postings were found.")

    if args.rank:
        ranked = rank_postings(postings, resume_text)
        output = [{k: a[k] for k in ("company", "title", "score", "score_label", "summary")} for a in ranked]
        for row in output:
            print(f"{row['score'] if row['score'] is not None else '--':>4}  {row['company']} - {row['title']}")
    else:
        if not 0 <= args.posting_index < len(postings):
            raise IndexError(f"Posting index must be between 0 and {len(postings) - 1}.")
        output = analyze_posting(postings[args.posting_index], resume_text)
        print(f"Analyzed: {output['company']} - {output['title']}")
        print(f"Score: {output['score']}  Summary: {output['summary']}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved results to: {args.output}")


if __name__ == "__main__":
    main()
