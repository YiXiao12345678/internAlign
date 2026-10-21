"""
Offline tests for the RAG workflow. They use a fake embedding model and a fake
language model, so no downloads, API keys or network are needed.

Run from the project root:  pytest ai-workflow/tests
"""
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("faiss")
pytest.importorskip("langchain_community")
pytest.importorskip("fastapi")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.embeddings import DeterministicFakeEmbedding  # noqa: E402

from internalign_rag import analysis, config, knowledge_base  # noqa: E402
from internalign_rag.router import build_router  # noqa: E402

RESUME = """Jane Student
Skills
Python, Java, SQL

Projects
Built a Flask web app that tracks club events and deployed it on Heroku.
Wrote unit tests with pytest for the scheduling module.
"""

POSTINGS = [
    {
        "id": "greenhouse:acme:1", "company": "Acme", "title": "Backend Intern",
        "location": "San Jose, CA", "url": "https://example.com/1",
        "text": "Required: Python and SQL. Preferred: Docker and AWS. You will build REST APIs.",
    },
    {
        "id": "lever:beta:2", "company": "Beta", "title": "Frontend Intern",
        "location": "Remote", "url": "https://example.com/2",
        "text": "Required: JavaScript and React. You will build user interfaces.",
    },
]


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.reply


@pytest.fixture()
def index(tmp_path, monkeypatch):
    postings_file = tmp_path / "postings.jsonl"
    postings_file.write_text("\n".join(json.dumps(p) for p in POSTINGS), encoding="utf-8")
    monkeypatch.setattr(config, "VECTOR_DB_PATH", tmp_path / "qdrant")
    monkeypatch.setattr(config, "POSTINGS_PATH", postings_file)
    knowledge_base.reset()
    knowledge_base.set_embeddings(DeterministicFakeEmbedding(size=32))
    knowledge_base.build_index()
    yield
    knowledge_base.reset()
    knowledge_base.set_embeddings(None)


def test_search_before_index_is_built(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VECTOR_DB_PATH", tmp_path / "missing")
    knowledge_base.reset()
    with pytest.raises(knowledge_base.IndexNotBuilt):
        knowledge_base.search("python")


def test_index_and_search(index):
    assert knowledge_base.chunk_count() >= 2
    hits = knowledge_base.search("python sql backend", k=5)
    assert hits
    only_beta = knowledge_base.search("anything", k=5, posting_id="lever:beta:2")
    assert only_beta
    for hit in only_beta:
        assert hit["posting_id"] == "lever:beta:2"


def test_posting_metadata(index):
    assert knowledge_base.posting_metadata("greenhouse:acme:1")["company"] == "Acme"
    assert knowledge_base.posting_metadata("nope") is None


def test_match_postings_returns_each_posting_once(index):
    ranked = knowledge_base.match_postings(["Python and SQL projects", "React interfaces"], top_postings=5)
    ids = []
    for item in ranked:
        ids.append(item["posting_id"])
    assert sorted(ids) == sorted(set(ids))
    assert len(ids) == 2


def test_parse_json_reply_handles_code_fences():
    reply = 'Sure!\n```json\n{"requirements": [{"requirement": "Python"}]}\n```'
    assert analysis.parse_json_reply(reply)["requirements"][0]["requirement"] == "Python"


def test_parse_json_reply_rejects_garbage():
    with pytest.raises(analysis.AnalysisError):
        analysis.parse_json_reply("I cannot do that.")
    with pytest.raises(analysis.AnalysisError):
        analysis.parse_json_reply('{"something": 1}')


def test_fabricated_evidence_is_removed_and_status_downgraded():
    raw = [
        {"requirement": "Docker", "importance": "required", "status": "Supported",
         "evidence": ["Deployed microservices with Docker and Kubernetes at Google"]},
        {"requirement": "Python", "importance": "required", "status": "Supported",
         "evidence": ["- Python, Java, SQL"]},
    ]
    results, removed = analysis.verify_requirements(raw, RESUME)
    by_name = {}
    for result in results:
        by_name[result["requirement"]] = result
    assert by_name["Docker"]["status"] == "Not found"
    assert by_name["Docker"]["resume_evidence"] == []
    assert by_name["Docker"]["clarification"]["kind"] == "missing"
    assert by_name["Python"]["status"] == "Supported"
    assert by_name["Python"]["evidence_type"] == "listed"
    assert removed == 1


def test_partial_without_real_evidence_becomes_not_found():
    raw = [{"requirement": "Spring", "importance": "preferred", "status": "Partially supported",
            "related_skill": "Java", "evidence": ["Led a Java team of ten engineers"]}]
    results, _ = analysis.verify_requirements(raw, RESUME)
    assert results[0]["status"] == "Not found"
    assert results[0]["related_skill"] is None


def test_bad_values_are_normalized():
    raw = [{"requirement": "SQL", "importance": "mandatory", "status": "maybe", "evidence": "SQL"}]
    results, _ = analysis.verify_requirements(raw, RESUME)
    assert results[0]["importance"] == "required"
    assert results[0]["status"] == "Not found"


def test_score_matches_rule_based_weighting():
    results = [
        {"importance": "required", "status": "Supported"},
        {"importance": "required", "status": "Not found"},
        {"importance": "preferred", "status": "Partially supported"},
    ]
    # earned 1 + 0 + 0.25 of total 2.5
    assert analysis.score_requirements(results) == 50
    assert analysis.score_label(50) == "Partial match"
    assert analysis.score_requirements([]) is None


def test_analyze_end_to_end_with_fake_llm(index):
    reply = json.dumps({"requirements": [
        {"requirement": "Python", "importance": "required", "status": "Supported",
         "evidence": ["Python, Java, SQL"], "question": ""},
        {"requirement": "SQL", "importance": "required", "status": "Supported",
         "evidence": ["Python, Java, SQL"], "question": ""},
        {"requirement": "Docker", "importance": "preferred", "status": "Supported",
         "evidence": ["Containerized everything with Docker"], "question": ""},
        {"requirement": "AWS", "importance": "preferred", "status": "Not found",
         "evidence": [], "question": "Have you used AWS in a class or project?"},
    ]})
    model = FakeLLM(reply)
    result = analysis.analyze(RESUME, "greenhouse:acme:1", model=model)

    assert result["company"] == "Acme"
    assert result["engine"] == "rag"
    assert result["summary"]["Supported"] == 2
    assert result["summary"]["Not found"] == 2          # Docker was downgraded
    assert result["unverified_quotes_removed"] == 1
    assert result["score"] == 67                        # (1 + 1) / (1 + 1 + 0.5 + 0.5)
    assert "REST APIs" in model.prompts[0]              # posting text reached the prompt
    assert "Flask web app" in model.prompts[0]          # resume text reached the prompt
    questions = []
    for item in result["clarification_questions"]:
        questions.append(item["requirement"])
    assert "AWS" in questions and "Docker" in questions


def test_requirement_must_appear_in_posting():
    posting = "Required: Python and SQL. You will build REST APIs with a collaborative team."
    assert analysis.is_in_posting("Python", posting)
    assert analysis.is_in_posting("REST APIs", posting)
    assert analysis.is_in_posting("Collaboration", posting)      # collaborative ~ collaboration
    assert not analysis.is_in_posting("Git", posting)            # not mentioned
    assert not analysis.is_in_posting("HTML/CSS", posting)
    assert not analysis.is_in_posting("Digital Marketing", posting)
    assert not analysis.is_in_posting("Git", "A digital team")   # no substring accidents


def test_resume_skills_not_in_posting_are_dropped(index):
    reply = json.dumps({"requirements": [
        {"requirement": "Python", "importance": "required", "status": "Supported",
         "evidence": ["Python, Java, SQL"]},
        {"requirement": "Git", "importance": "preferred", "status": "Supported",
         "evidence": ["Python, Java, SQL"]},
        {"requirement": "Flask", "importance": "preferred", "status": "Supported",
         "evidence": ["Built a Flask web app that tracks club events and deployed it on Heroku."]},
    ]})
    result = analysis.analyze(RESUME, "greenhouse:acme:1", model=FakeLLM(reply))
    names = []
    for item in result["requirements"]:
        names.append(item["requirement"])
    assert names == ["Python"]
    assert result["ungrounded_requirements_removed"] == 2


def test_analyze_unknown_posting(index):
    with pytest.raises(KeyError):
        analysis.analyze(RESUME, "does-not-exist", model=FakeLLM("{}"))


def _client(resume_text=RESUME):
    def fake_auth():
        return "user"

    def fake_db():
        return "db"

    def load_resume(user, db):
        if resume_text is None:
            raise HTTPException(status_code=404, detail="Upload a resume first.")
        return resume_text

    app = FastAPI()
    app.include_router(build_router(fake_auth, fake_db, load_resume))
    return TestClient(app)


def test_routes_return_503_when_index_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VECTOR_DB_PATH", tmp_path / "missing")
    knowledge_base.reset()
    client = _client()
    assert client.get("/rag/status").json()["index_built"] is False
    response = client.get("/rag/analysis/greenhouse:acme:1")
    assert response.status_code == 503
    assert "index" in response.json()["detail"].lower()


def test_routes_match_and_unknown_posting(index):
    client = _client()
    assert client.get("/rag/status").json()["index_built"] is True
    matches = client.get("/rag/matches?limit=5").json()
    assert matches["total"] == 2
    assert client.get("/rag/analysis/not-a-posting").status_code == 404


def test_route_requires_resume(index):
    client = _client(resume_text=None)
    assert client.get("/rag/analysis/greenhouse:acme:1").status_code == 404
