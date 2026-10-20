from backend.job_parser import parse_posting, split_posting_sections
from backend.resume_parser import (
    ResumeParseError,
    extract_text_from_bytes,
    split_sections,
)

POSTING = {
    "id": "x:1",
    "company": "Acme",
    "title": "SWE Intern",
    "text": (
        "Acme builds rockets.\n\n"
        "Responsibilities\n"
        "- Build services in Go or C++\n"
        "-\n"
        "- Debug Linux systems\n\n"
        "Qualifications\n"
        "- Experience with Python\n\n"
        "Nice to have\n"
        "- Kubernetes\n"
    ),
}


def test_posting_sections_and_required_vs_preferred():
    parsed = parse_posting(POSTING)
    assert "python" in parsed["required_skills"]
    assert "go" in parsed["required_skills"]
    assert parsed["preferred_skills"] == ["kubernetes"]
    assert "Build services in Go or C++" in parsed["responsibilities"]


def test_bare_bullets_are_dropped():
    sections = split_posting_sections(POSTING["text"])
    assert "" not in sections["responsibilities"]
    assert "-" not in sections["responsibilities"]


RESUME = (
    "Yi Xiao\nSKILLS\nPython, Java, SQL\nEXPERIENCE\n"
    "• Built a Python validation tool for RF test data\nPROJECTS\n• Wrote a Flask REST API"
)


def test_resume_sections():
    sections = split_sections(RESUME)
    assert sections["skills"] == ["Python, Java, SQL"]
    assert sections["experience"] == ["• Built a Python validation tool for RF test data"]
    assert "projects" in sections


def test_resume_txt_upload_and_errors():
    assert "Python" in extract_text_from_bytes(RESUME.encode(), "resume.txt")
    for data, name in [(b"", "r.txt"), (b"hello", "r.txt"), (RESUME.encode(), "r.exe")]:
        try:
            extract_text_from_bytes(data, name)
        except ResumeParseError:
            continue
        raise AssertionError(f"expected ResumeParseError for {name!r}")
