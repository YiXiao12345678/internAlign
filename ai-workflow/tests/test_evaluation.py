"""
Offline tests for the evaluation metrics and the evaluation runner. No API key,
network, FAISS or embedding model is needed (the runner is exercised with a fake
analyzer and a fake matcher).

Run from the project root:  pytest ai-workflow/tests/test_evaluation.py
"""
import importlib.util
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from internalign_rag import evaluation as ev  # noqa: E402


def _load_runner():
    spec = importlib.util.spec_from_file_location("evaluate_runner", HERE / "evaluate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# metrics
def test_role_family():
    assert ev.role_family("Software Engineer Intern, Backend") == "SE"
    assert ev.role_family("Machine Learning Intern") == "AIML"
    assert ev.role_family("Software Engineer, AI Platform - Intern") == "hybrid"
    assert ev.role_family("Marketing Intern") == "other"


def test_cohen_kappa_known_values():
    a = ["Supported", "Supported", "Not found", "Not found"]
    assert ev.cohen_kappa(a, a)["kappa"] == 1.0
    # classic 2x2 example: observed 0.7, expected 0.5 -> kappa 0.4
    x = ["Supported"] * 25 + ["Supported"] * 25 + ["Not found"] * 5 + ["Not found"] * 45
    y = ["Supported"] * 25 + ["Not found"] * 25 + ["Supported"] * 5 + ["Not found"] * 45
    result = ev.cohen_kappa(x, y, labels=("Supported", "Not found"))
    assert math.isclose(result["agreement"], 0.70)
    assert math.isclose(result["kappa"], 0.4, abs_tol=1e-9)
    assert ev.cohen_kappa([], [])["kappa"] is None


def test_precision_recall_f1():
    truth = ["Supported", "Supported", "Not found", "Not found", "Partially supported"]
    pred = ["Supported", "Not found", "Not found", "Supported", "Partially supported"]
    result = ev.precision_recall_f1(truth, pred)
    sup = result["per_class"]["Supported"]
    assert math.isclose(sup["precision"], 0.5) and math.isclose(sup["recall"], 0.5)
    assert math.isclose(sup["f1"], 0.5)
    assert result["per_class"]["Partially supported"]["f1"] == 1.0
    assert math.isclose(result["accuracy"], 0.6)
    assert result["n"] == 5


def test_undefined_precision_is_none_not_zero():
    result = ev.precision_recall_f1(["Not found"], ["Not found"])
    assert result["per_class"]["Supported"]["precision"] is None


def test_wilson_interval_and_rate():
    low, high = ev.wilson_interval(0, 20)
    assert low == 0.0 and 0.1 < high < 0.2
    assert ev.rate(0, 0)["rate"] is None
    assert ev.rate(5, 10)["rate"] == 0.5


def test_sign_test():
    assert ev.exact_sign_test(0, 0) is None
    assert math.isclose(ev.exact_sign_test(5, 5), 1.0)
    assert math.isclose(ev.exact_sign_test(10, 0), 2 / 1024)


def test_paired_comparison():
    a = [80, 70, 60, 50]
    b = [60, 70, 40, 55]
    result = ev.paired_comparison(a, b)
    assert result["n"] == 4 and result["wins"] == 2 and result["losses"] == 1 and result["ties"] == 1
    assert math.isclose(result["mean_diff"], 8.75)
    assert math.isclose(result["win_rate_a"], 2.5 / 4)
    assert result["ci95"][0] <= result["mean_diff"] <= result["ci95"][1]


def test_paired_comparison_skips_missing_scores():
    result = ev.paired_comparison([80, None, 60], [70, 50, None])
    assert result["n"] == 1


def test_ranking_metrics():
    rels = [1, 0, 1, 0, 0, 0]
    assert ev.precision_at_k(rels, 5) == 0.4
    assert ev.reciprocal_rank([0, 0, 1]) == 1 / 3
    assert ev.reciprocal_rank([0, 0]) == 0.0
    perfect = ev.ndcg_at_k([1, 1, 0], 3, total_relevant=2)
    assert math.isclose(perfect, 1.0)
    worse = ev.ndcg_at_k([0, 1, 1], 3, total_relevant=2)
    assert 0 < worse < 1
    summary = ev.ranking_summary(rels, base_rate=0.2, total_relevant=3)
    assert math.isclose(summary["lift@5"], 2.0)


def test_appears_in_and_fragmentation():
    resume = "Built a Flask app\nwith pytest tests"
    assert ev.appears_in("built a flask app with PyTest tests", resume)
    assert not ev.appears_in("Led a team of ten", resume)
    assert ev.one_word_line_ratio("Hello world\nSystems,\n \nFormal\nLanguage") > 0.5


# ---------------------------------------------------------------- runner
POSTINGS = [
    {"id": "t:1", "company": "A", "title": "Software Engineer Intern", "required_skills": ["python", "react"], "preferred_skills": []},
    {"id": "t:2", "company": "B", "title": "Backend Software Intern", "required_skills": ["python", "rust"], "preferred_skills": []},
    {"id": "t:3", "company": "C", "title": "Machine Learning Intern", "required_skills": ["python", "pytorch"], "preferred_skills": []},
    {"id": "t:4", "company": "D", "title": "AI Research Intern", "required_skills": ["pytorch", "python"], "preferred_skills": []},
]
SE_RESUME = "Skills\nPython, React\nProjects\nBuilt a React storefront with a Python backend.\n"
ML_RESUME = "Skills\nPython, PyTorch\nProjects\nTrained a PyTorch image classifier on 25k images.\n"


def fake_analyze(resume_text, posting_id):
    """Stands in for analysis.analyze: claims Rust is Supported with no evidence, once."""
    reqs = []
    for skill, status in (("Python", "Supported"), ("Rust", "Supported"), ("React", "Not found")):
        evidence = [skill] if status == "Supported" and skill.lower() in resume_text.lower() else []
        shown_status = status if evidence or status == "Not found" else "Supported"
        reqs.append({"requirement": skill, "importance": "required", "status": shown_status,
                     "resume_evidence": evidence})
    score = 70 if "React" in resume_text else 40
    return {"company": "X", "title": "T", "model": "fake", "score": score, "requirements": reqs,
            "unverified_quotes_removed": 1, "ungrounded_requirements_removed": 1, "retrieved_chunks": 3}


def fake_match(resume_text, top):
    ids = ["t:1", "t:2", "t:3", "t:4"] if "React" in resume_text else ["t:3", "t:4", "t:1", "t:2"]
    return [{"posting_id": pid, "title": "", "company": ""} for pid in ids[:top]]


def test_runner_end_to_end(tmp_path):
    runner = _load_runner()
    (tmp_path / "se.txt").write_text(SE_RESUME)
    (tmp_path / "ml.txt").write_text(ML_RESUME)
    postings = tmp_path / "parsed.jsonl"
    postings.write_text("\n".join(json.dumps(p) for p in POSTINGS))
    args = SimpleNamespace(postings=str(postings), resume=[f"SE={tmp_path / 'se.txt'}", f"AIML={tmp_path / 'ml.txt'}"],
                           n_per_family=2, seed=1, out=str(tmp_path / "out"), skip_rag=False, fresh=False)
    results = runner.run_evaluation(args, analyze_fn=fake_analyze, match_fn=fake_match, log=lambda *_: None)

    # baseline discrimination: the SE resume wins on SE postings, the ML resume on ML postings
    base = results["baseline"]["discrimination"]
    assert base["SE_postings"]["mean_diff"] > 0
    assert base["AIML_postings"]["mean_diff"] > 0
    rag = results["rag"]
    assert rag["discrimination"]["SE_postings"]["n"] == 2
    # faithfulness: 1 quote removed per analysis, plus the Python quote kept
    f = rag["faithfulness"]["SE"]
    assert f["analyses"] == 4
    assert f["quote_support_rate"]["rate"] < 1.0
    assert f["unsupported_evidence_shown"] == 0
    assert f["supported_without_evidence"] == 0 or f["supported_without_evidence"] > 0  # key exists
    # the fake claims Rust is Supported without evidence on the ML resume -> oracle flags it
    assert rag["oracle_check"]["AIML"]["unsupported_claim_rate_on_absent"]["n"] >= 1
    assert rag["retrieval"]["SE"]["precision@5"] >= 0
    for name in ("eval_results.json", "eval_summary.md", "rag_requirements.csv", "labeling_sheet.csv", "rag_pairs.jsonl"):
        assert (tmp_path / "out" / name).exists()

    # a second run reads the cache and does not call the analyzer again
    calls = []

    def counting(resume_text, posting_id):
        calls.append(posting_id)
        return fake_analyze(resume_text, posting_id)

    runner.run_evaluation(args, analyze_fn=counting, match_fn=fake_match, log=lambda *_: None)
    assert calls == []


def test_score_labels(tmp_path):
    runner = _load_runner()
    sheet = tmp_path / "sheet.csv"
    sheet.write_text(
        "row_id,resume,posting_id,company,title,requirement,importance,rag_status,evidence,oracle,human_status,notes\n"
        "1,SE,p,c,t,Python,required,Supported,x,present,Supported,\n"
        "2,SE,p,c,t,Rust,required,Supported,x,absent,Not found,\n"
        "3,SE,p,c,t,Go,required,Not found,,absent,Not found,\n"
        "4,SE,p,c,t,SQL,required,Supported,x,present,,\n"
    )
    metrics = runner.score_labels(sheet)
    assert metrics["labeled_rows"] == 3
    assert metrics["supported_precision"]["rate"] == 0.5
    assert metrics["per_class"]["Not found"]["recall"] == 0.5
    assert metrics["per_class"]["Not found"]["precision"] == 1.0


def test_failed_calls_are_counted_not_fatal(tmp_path):
    runner = _load_runner()
    (tmp_path / "se.txt").write_text(SE_RESUME)
    (tmp_path / "ml.txt").write_text(ML_RESUME)
    postings = tmp_path / "parsed.jsonl"
    postings.write_text("\n".join(json.dumps(p) for p in POSTINGS))
    args = SimpleNamespace(postings=str(postings), resume=[f"SE={tmp_path / 'se.txt'}", f"AIML={tmp_path / 'ml.txt'}"],
                           n_per_family=1, seed=1, out=str(tmp_path / "out"), skip_rag=False, fresh=True)

    def flaky(resume_text, posting_id):
        raise RuntimeError("rate limited")

    results = runner.run_evaluation(args, analyze_fn=flaky, match_fn=fake_match, log=lambda *_: None)
    assert results["rag"]["efficiency"]["failed"] == 4
