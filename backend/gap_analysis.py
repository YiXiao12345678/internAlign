from pathlib import Path
import argparse
import json
import re

from .resume_parser import extract_resume_text


def read_jsonl(file_path: str) -> list[dict]:
    postings = []

    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if line:
                postings.append(json.loads(line))

    return postings


def find_evidence(skill: str, resume_text: str) -> list[str]:
    """Return resume lines that mention the skill."""
    pattern = r"(?<!\w)" + re.escape(skill.lower()) + r"(?!\w)"
    evidence = []

    for line in resume_text.splitlines():
        clean_line = line.strip()

        if clean_line and re.search(pattern, clean_line.lower()):
            evidence.append(clean_line)

    return evidence[:3]


def analyze_skill(skill: str, resume_text: str) -> dict:
    skill_evidence = find_evidence(skill, resume_text)

    if skill_evidence:
        status = "Supported"
        evidence = skill_evidence
    elif " " in skill:
        # For phrases such as "machine learning" or "data structures",
        # check whether part of the phrase appears.
        words = skill.lower().split()
        partial_evidence = []

        for line in resume_text.splitlines():
            clean_line = line.strip()
            lower_line = clean_line.lower()

            if clean_line and any(
                re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", lower_line)
                for word in words
            ):
                partial_evidence.append(clean_line)

        if partial_evidence:
            status = "Partially supported"
            evidence = partial_evidence[:3]
        else:
            status = "Not found"
            evidence = []
    else:
        status = "Not found"
        evidence = []

    return {
        "requirement": skill,
        "status": status,
        "resume_evidence": evidence,
    }


def analyze_posting(posting: dict, resume_text: str) -> dict:
    skills = posting.get("skills_mentioned", [])

    results = [
        analyze_skill(skill, resume_text)
        for skill in skills
    ]

    summary = {
        "Supported": 0,
        "Partially supported": 0,
        "Not found": 0,
    }

    for result in results:
        summary[result["status"]] += 1

    return {
        "company": posting.get("company", ""),
        "title": posting.get("title", ""),
        "job_url": posting.get("url", ""),
        "summary": summary,
        "requirements": results,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Compare a resume with a parsed job posting."
    )

    parser.add_argument(
        "--resume",
        required=True,
        help="Path to the resume PDF",
    )

    parser.add_argument(
        "--job",
        default="data/parsed_postings.jsonl",
        help="Path to parsed job postings",
    )

    parser.add_argument(
        "--posting-index",
        type=int,
        default=0,
        help="Which posting to analyze; starts at 0",
    )

    parser.add_argument(
        "--output",
        default="data/gap_analysis.json",
        help="Output JSON file",
    )

    args = parser.parse_args()

    resume_text = extract_resume_text(args.resume)
    postings = read_jsonl(args.job)

    if not postings:
        raise ValueError("No parsed job postings were found.")

    if args.posting_index >= len(postings):
        raise IndexError(
            f"Posting index must be between 0 and {len(postings) - 1}."
        )

    selected_posting = postings[args.posting_index]
    analysis = analyze_posting(selected_posting, resume_text)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(analysis, file, indent=2, ensure_ascii=False)

    print(f"Analyzed: {analysis['company']} - {analysis['title']}")
    print(f"Summary: {analysis['summary']}")
    print(f"Saved results to: {args.output}")


if __name__ == "__main__":
    main()