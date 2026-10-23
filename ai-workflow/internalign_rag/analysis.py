"""
RAG gap analysis (Component 2).

1. Retrieve the most relevant chunks of the chosen posting from the vector store.
2. Ask the language model to list the posting's requirements and compare each
   with the resume, quoting the resume line that proves it.
3. Check every quote against the real resume text. A requirement the model
   claims is supported, but cannot back with a real resume line, is downgraded
   to "Not found". This is the truthfulness guard: nothing unsupported survives.

The result has the same shape as backend/gap_analysis.analyze_posting, so the
existing dashboard can display it and the two methods can be compared.
"""
from __future__ import annotations

import json
import re

from . import config, knowledge_base, llm

SUPPORTED = "Supported"
PARTIAL = "Partially supported"
NOT_FOUND = "Not found"
STATUSES = (SUPPORTED, PARTIAL, NOT_FOUND)

IMPORTANCE_WEIGHT = {"required": 1.0, "preferred": 0.5}
STATUS_CREDIT = {SUPPORTED: 1.0, PARTIAL: 0.5, NOT_FOUND: 0.0}

POSTING_QUERIES = [
    "required qualifications and skills",
    "preferred qualifications nice to have",
    "responsibilities what you will do",
    "programming languages tools and technologies",
]
MAX_POSTING_CHUNKS = 8
MAX_REQUIREMENTS = 12

PROMPT = """You compare a student's resume with one internship posting.

Rules:
- Use ONLY the resume text below. Never invent experience, tools, projects or numbers.
- List the skills, technologies and qualifications the POSTING asks for (at most {max_requirements}).
  Mark each "required" or "preferred". Only list what the posting excerpts actually state. Never add
  a skill just because the resume mentions it.
- Give each a status:
  "Supported": the resume clearly shows it.
  "Partially supported": the resume shows a closely related skill; name it in related_skill.
  "Not found": no evidence in the resume.
- evidence: copy up to 2 lines EXACTLY as written in the resume. If you cannot quote the
  resume, the status must be "Not found" and evidence must be empty.
- question: for "Partially supported" and "Not found", one short question asking whether the
  student has this experience (never assume they do). Otherwise leave it empty.

Reply with ONLY this JSON and nothing else:
{{"requirements": [{{"requirement": "Python", "importance": "required", "status": "Supported", "related_skill": "", "evidence": ["exact resume line"], "question": ""}}]}}

POSTING EXCERPTS:
{posting}

RESUME:
{resume}
"""


class AnalysisError(Exception):
    """Raised when the model's reply cannot be turned into an analysis."""


def resume_queries(resume_text: str, max_queries: int = 6, block_chars: int = 700) -> list[str]:
    """Split a resume into a few text blocks, used as retrieval queries."""
    blocks = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", resume_text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if current and len(current) + len(paragraph) > block_chars:
            blocks.append(current)
            current = ""
        current = (current + "\n" + paragraph).strip()
    if current:
        blocks.append(current)
    result = []
    for block in blocks[:max_queries]:
        result.append(block[:block_chars])
    return result


def retrieve_posting_context(posting_id: str) -> list[dict]:
    """The most relevant chunks of one posting, in reading order."""
    chosen: dict[int, dict] = {}
    for query in POSTING_QUERIES:
        for hit in knowledge_base.search(query, k=4, posting_id=posting_id):
            chosen[hit["chunk_index"]] = hit
    ordered = []
    for index in sorted(chosen):
        ordered.append(chosen[index])
    return ordered[:MAX_POSTING_CHUNKS]


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9+#]+", " ", text.lower()).strip()


def is_in_resume(quote: str, resume_text: str) -> bool:
    """True if `quote` really appears in the resume (ignoring case, bullets and spacing)."""
    needle = _normalize(quote)
    if len(needle) < 3:
        return False
    return needle in _normalize(resume_text)


_FILLER_WORDS = {"and", "the", "for", "with", "from", "that", "this", "into", "such", "related"}


def _words(text: str) -> list[str]:
    return _normalize(text).split()


def is_in_posting(requirement: str, posting_text: str) -> bool:
    posting_words = _words(posting_text)
    exact = set(posting_words)
    wanted = 0
    for word in _words(requirement):
        if word in _FILLER_WORDS or (len(word) < 2 and word not in ("c", "r")):
            continue
        wanted += 1
        if len(word) >= 5:
            prefix = word[:5]
            found = False
            for candidate in posting_words:
                if candidate.startswith(prefix):
                    found = True
                    break
            if not found:
                return False
        elif word not in exact:
            return False
    return wanted > 0


def keep_grounded_requirements(raw_requirements: list, posting_text: str) -> tuple[list, int]:
    """Drop requirements the posting never states (the model echoing the resume back)."""
    kept = []
    dropped = 0
    for item in raw_requirements:
        name = ""
        if isinstance(item, dict):
            name = str(item.get("requirement", ""))
        if name and is_in_posting(name, posting_text):
            kept.append(item)
        else:
            dropped += 1
    return kept, dropped


def parse_json_reply(reply: str) -> dict:
    """Pull the JSON object out of a model reply, tolerating code fences and extra prose."""
    start = reply.find("{")
    end = reply.rfind("}")
    if start == -1 or end <= start:
        raise AnalysisError("The model did not return JSON.")
    try:
        data = json.loads(reply[start : end + 1])
    except json.JSONDecodeError as error:
        raise AnalysisError(f"The model returned malformed JSON: {error}")
    if not isinstance(data, dict) or not isinstance(data.get("requirements"), list):
        raise AnalysisError("The model's JSON has no 'requirements' list.")
    return data


def _evidence_type(lines: list[str]) -> str | None:
    """Short lines look like a skills list; longer ones describe work actually done."""
    if not lines:
        return None
    for line in lines:
        if len(line.split()) >= 8:
            return "demonstrated"
    return "listed"


def verify_requirements(raw_requirements: list, resume_text: str) -> tuple[list[dict], int]:
    """Clean the model's requirements and enforce the truthfulness rule."""
    results = []
    removed = 0
    seen = set()
    for item in raw_requirements:
        if not isinstance(item, dict):
            continue
        name = str(item.get("requirement", "")).strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        importance = str(item.get("importance", "required")).lower()
        if importance not in IMPORTANCE_WEIGHT:
            importance = "required"
        status = str(item.get("status", NOT_FOUND)).strip()
        if status not in STATUSES:
            status = NOT_FOUND

        verified = []
        raw_evidence = item.get("evidence", [])
        if not isinstance(raw_evidence, list):
            raw_evidence = [raw_evidence]
        for quote in raw_evidence:
            quote = str(quote).strip()
            if quote and is_in_resume(quote, resume_text):
                verified.append(quote)
            elif quote:
                removed += 1

        if status in (SUPPORTED, PARTIAL) and not verified:
            status = NOT_FOUND
        if status == NOT_FOUND:
            verified = []

        related = str(item.get("related_skill", "")).strip() or None
        if status != PARTIAL:
            related = None
        evidence_type = _evidence_type(verified) if status == SUPPORTED else None

        question = str(item.get("question", "")).strip()
        clarification = None
        if status != SUPPORTED and not question:
            question = f"Have you used {name}, or something similar? If so, where and what was your role?"
        if status == SUPPORTED and evidence_type == "listed" and not question:
            question = f"{name} is in your skills list. Which project or role shows you using it?"
        if question:
            kind = "missing"
            if status == PARTIAL:
                kind = "partial"
            elif status == SUPPORTED:
                kind = "strengthen"
            clarification = {"kind": kind, "question": question}

        evidence = []
        for line in verified:
            evidence.append({"line": line, "section": "resume"})
        results.append(
            {
                "requirement": name,
                "display_name": name,
                "importance": importance,
                "status": status,
                "evidence_type": evidence_type,
                "related_skill": related,
                "resume_evidence": verified,
                "evidence": evidence,
                "clarification": clarification,
            }
        )
        if len(results) >= MAX_REQUIREMENTS:
            break
    return results, removed


def score_requirements(results: list[dict]) -> int | None:
    total = 0.0
    earned = 0.0
    for result in results:
        weight = IMPORTANCE_WEIGHT[result["importance"]]
        total += weight
        earned += weight * STATUS_CREDIT[result["status"]]
    if not total:
        return None
    return round(100 * earned / total)


def score_label(score: int | None) -> str:
    # Same bands as backend/gap_analysis.score_label, so both methods read alike.
    if score is None:
        return "Not enough detail"
    if score >= 85:
        return "Excellent match"
    if score >= 70:
        return "Strong match"
    if score >= 50:
        return "Partial match"
    return "Stretch"


def _sort_key(result: dict) -> tuple:
    order = {NOT_FOUND: 0, PARTIAL: 1, SUPPORTED: 2}
    return (result["importance"] != "required", order[result["status"]], result["requirement"])


def build_prompt(context: list[dict], resume_text: str) -> str:
    excerpts = []
    for hit in context:
        excerpts.append(hit["text"])
    return PROMPT.format(
        max_requirements=MAX_REQUIREMENTS,
        posting="\n---\n".join(excerpts),
        resume=resume_text[: config.MAX_RESUME_CHARS],
    )


def analyze(resume_text: str, posting_id: str, model=None) -> dict:
    """Run the full RAG gap analysis for one posting."""
    metadata = knowledge_base.posting_metadata(posting_id)
    if metadata is None:
        raise KeyError(posting_id)

    context = retrieve_posting_context(posting_id)
    reply = llm.ask(build_prompt(context, resume_text), llm=model)
    data = parse_json_reply(reply)
    grounded, ungrounded = keep_grounded_requirements(
        data["requirements"], knowledge_base.posting_text(posting_id)
    )
    results, removed = verify_requirements(grounded, resume_text)
    results.sort(key=_sort_key)

    summary = {SUPPORTED: 0, PARTIAL: 0, NOT_FOUND: 0}
    questions = []
    for result in results:
        summary[result["status"]] += 1
        if result["clarification"]:
            question = dict(result["clarification"])
            question["requirement"] = result["requirement"]
            questions.append(question)

    score = score_requirements(results)
    note = None
    if not results:
        note = "The model did not find specific requirements in this posting, so a match score isn't available."
    return {
        "engine": "rag",
        "model": llm.last_model_used or llm.model_name(),
        "posting_id": posting_id,
        "company": metadata.get("company", ""),
        "title": metadata.get("title", ""),
        "location": metadata.get("location", ""),
        "job_url": metadata.get("url", ""),
        "score": score,
        "score_label": score_label(score),
        "summary": summary,
        "requirements": results,
        "clarification_questions": questions,
        "retrieved_chunks": len(context),
        "unverified_quotes_removed": removed,
        "ungrounded_requirements_removed": ungrounded,
        "note": note,
    }
