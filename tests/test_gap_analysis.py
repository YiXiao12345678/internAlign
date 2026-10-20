from backend.gap_analysis import NOT_FOUND, PARTIAL, SUPPORTED, analyze_posting, rank_postings

RESUME = """Sam Student
SKILLS
Python, Java, SQL, C++
EXPERIENCE
• Built a Python tool that validates RF test logs
PROJECTS
• Trained a PyTorch image classifier
"""

POSTING = {
    "id": "x:1",
    "company": "Acme",
    "title": "SWE Intern",
    "required_skills": ["python", "c++", "machine learning", "rust"],
    "preferred_skills": ["java"],
}


def by_skill(analysis):
    return {r["requirement"]: r for r in analysis["requirements"]}


def test_statuses():
    result = by_skill(analyze_posting(POSTING, RESUME))
    assert result["python"]["status"] == SUPPORTED
    assert result["python"]["evidence_type"] == "demonstrated"
    assert result["c++"]["status"] == SUPPORTED
    assert result["c++"]["evidence_type"] == "listed"
    assert result["machine learning"]["status"] == PARTIAL
    assert result["machine learning"]["related_skill"] == "pytorch"
    assert result["rust"]["status"] == NOT_FOUND


def test_evidence_is_verbatim_resume_text():
    result = by_skill(analyze_posting(POSTING, RESUME))
    for req in result.values():
        for line in req["resume_evidence"]:
            assert line in RESUME


def test_every_gap_gets_a_question_and_supported_demonstrated_does_not():
    result = by_skill(analyze_posting(POSTING, RESUME))
    assert result["rust"]["clarification"]["kind"] == "missing"
    assert result["machine learning"]["clarification"]["kind"] == "partial"
    assert result["c++"]["clarification"]["kind"] == "strengthen"
    assert result["python"]["clarification"] is None


def test_score_weights_required_over_preferred():
    analysis = analyze_posting(POSTING, RESUME)
    # required: 1 + 1 + 0.5 + 0 = 2.5 of 4 ; preferred: 0.5 of 0.5 -> 3.0 / 4.5
    assert analysis["score"] == 67


def test_posting_without_skills_has_no_score():
    analysis = analyze_posting({"id": "y", "company": "B", "title": "T"}, RESUME)
    assert analysis["score"] is None
    assert analysis["note"]


def test_ranking_orders_best_first_and_unscored_last():
    easy = {"id": "a", "company": "A", "title": "T", "required_skills": ["python"]}
    hard = {"id": "b", "company": "B", "title": "T", "required_skills": ["rust"]}
    empty = {"id": "c", "company": "C", "title": "T"}
    ranked = rank_postings([empty, hard, easy], RESUME)
    assert [a["posting_id"] for a in ranked] == ["a", "b", "c"]
