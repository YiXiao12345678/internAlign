from pathlib import Path
import argparse
import json
import re


KNOWN_SKILLS = [
    "python",
    "java",
    "c",
    "c++",
    "c#",
    "sql",
    "javascript",
    "typescript",
    "go",
    "rust",
    "kotlin",
    "swift",
    "git",
    "linux",
    "docker",
    "kubernetes",
    "aws",
    "gcp",
    "azure",
    "pandas",
    "pytorch",
    "tensorflow",
    "spark",
    "kafka",
    "react",
    "node.js",
    "rest api",
    "machine learning",
    "deep learning",
    "data structures",
    "algorithms",
]


def read_jsonl(file_path: str) -> list[dict]:
    """Read one JSON object per line."""
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


def extract_skills(text: str) -> list[str]:
    """Find known technical skills mentioned in the posting."""
    text_lower = text.lower()
    found_skills = []

    for skill in KNOWN_SKILLS:
        pattern = r"(?<!\w)" + re.escape(skill) + r"(?!\w)"

        if re.search(pattern, text_lower):
            found_skills.append(skill)

    return sorted(found_skills)


def matching_lines(text: str, keywords: list[str]) -> list[str]:
    """Return lines containing at least one keyword."""
    results = []

    for line in text.splitlines():
        clean_line = line.strip()

        if not clean_line:
            continue

        if any(keyword in clean_line.lower() for keyword in keywords):
            results.append(clean_line)

    return results


def parse_posting(posting: dict) -> dict:
    """Convert one raw posting into a structured record."""
    text = posting.get("text", "")

    return {
        "id": posting.get("id", ""),
        "company": posting.get("company", ""),
        "title": posting.get("title", ""),
        "location": posting.get("location", ""),
        "url": posting.get("url", ""),
        "skills_mentioned": extract_skills(text),
        "responsibilities": matching_lines(
            text,
            [
                "responsibilities",
                "you will",
                "you'll",
                "develop",
                "design",
                "build",
                "test",
                "debug",
                "maintain",
                "analyze",
            ],
        ),
        "qualification_lines": matching_lines(
            text,
            [
                "qualification",
                "requirement",
                "what you bring",
                "what we're looking for",
                "what we are looking for",
                "skills",
                "experience",
            ],
        ),
        "education_lines": matching_lines(
            text,
            [
                "bachelor",
                "master",
                "degree",
                "computer science",
                "coursework",
                "education",
            ],
        ),
        "experience_lines": matching_lines(
            text,
            [
                "experience",
                "internship",
                "intern",
                "co-op",
                "years",
            ],
        ),
    }


def write_jsonl(records: list[dict], file_path: str) -> None:
    """Write records as one JSON object per line."""
    output_path = Path(file_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Parse collected internship postings."
    )

    parser.add_argument(
        "--input",
        default="data/raw_postings.jsonl",
        help="Input JSONL file",
    )

    parser.add_argument(
        "--output",
        default="data/parsed_postings.jsonl",
        help="Output JSONL file",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of postings to process; 0 means all",
    )

    args = parser.parse_args()

    postings = read_jsonl(args.input)

    if args.limit > 0:
        postings = postings[:args.limit]

    parsed_postings = [parse_posting(posting) for posting in postings]
    write_jsonl(parsed_postings, args.output)

    print(f"Read {len(postings)} postings.")
    print(f"Wrote parsed results to {args.output}")


if __name__ == "__main__":
    main()