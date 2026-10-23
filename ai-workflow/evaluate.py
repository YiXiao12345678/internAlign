"""
Evaluation harness for InternAlign: rule-based baseline vs. the RAG analysis.

Run from the project root (virtual environment active, OPENAI_API_KEY in .env,
FAISS index built with `python ai-workflow/cli.py index`):

    python ai-workflow/evaluate.py run                      # ~60 GPT-4o-mini calls, a few minutes
    python ai-workflow/evaluate.py run --skip-rag           # baseline only, no API key needed
    python ai-workflow/evaluate.py run --n-per-family 25    # larger sample
    python ai-workflow/evaluate.py score-labels data/eval/labeling_sheet.csv

Outputs go to data/eval/: eval_results.json, eval_summary.md, rag_requirements.csv,
labeling_sheet.csv and rag_pairs.jsonl (a cache, so an interrupted run can resume).

What is measured (see ai-workflow/EVALUATION.md for the reasoning):

  1. Discrimination: does a resume's score for a posting depend on how well the resume fits
     it? SE resume vs AI/ML resume on SE postings and on AI/ML postings (paired comparison).
  2. Faithfulness: how much generated evidence was real (before the guard), and a post-guard
     audit that no unsupported evidence is shown.
  3. Unsupported-claim check against a keyword oracle: for requirements that map to one
     taxonomy skill, does RAG mark "Supported" when the resume never mentions it?
  4. Agreement with the rule-based baseline (Cohen's kappa) on the same requirements.
  5. Retrieval: Precision@5/10, nDCG@10, MRR for resume-to-posting matching, with the role
     family taken from the posting title as a weak relevance label, and lift over random.
  6. Efficiency: latency and an estimated cost per analysis.
  7. Human labels (optional): precision / recall / F1 per status from a labeling sheet.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

from internalign_rag import evaluation as ev  # noqa: E402

SUPPORTED, PARTIAL, NOT_FOUND = ev.STATUSES

DEFAULT_RESUMES = {
    "SE": "data/resume/yuji_n_resume_SE.pdf",
    "AIML": "data/resume/yuji_n_resume.pdf",
}
# Which role family each resume is written for (used as the relevance label for retrieval).
RESUME_FOCUS = {"SE": {"SE", "hybrid"}, "AIML": {"AIML", "hybrid"}}

# GPT-4o-mini list prices in USD per million tokens. Check the current price page before quoting.
PRICE_IN_PER_M = 0.15
PRICE_OUT_PER_M = 0.60


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_resumes(paths: dict[str, str]) -> dict[str, dict]:
    from backend.resume_parser import extract_resume_text

    resumes = {}
    for key, path in paths.items():
        full = Path(path)
        if not full.is_absolute():
            full = ROOT / full
        text = extract_resume_text(str(full))
        resumes[key] = {
            "path": str(path),
            "text": text,
            "chars": len(text),
            "one_word_line_ratio": ev.one_word_line_ratio(text),
        }
    return resumes


def sample_postings(postings: list[dict], n_per_family: int, seed: int) -> dict[str, list[str]]:
    """Stratified random sample of posting ids from the two strict role families."""
    rng = random.Random(seed)
    by_family = defaultdict(list)
    for posting in postings:
        family = ev.role_family(posting.get("title", ""))
        if family in ("SE", "AIML"):
            by_family[family].append(posting["id"])
    sample = {}
    for family in ("SE", "AIML"):
        ids = sorted(by_family[family])
        rng.shuffle(ids)
        sample[family] = ids[:n_per_family]
    return sample


# Baseline (rule-based)
def run_baseline(resumes: dict, postings: list[dict]) -> dict[str, dict[str, dict]]:
    from backend import gap_analysis

    return {
        key: {p["id"]: gap_analysis.analyze_posting(p, info["text"]) for p in postings}
        for key, info in resumes.items()
    }


def ranking_metrics(ranked_ids: list[str], family_by_id: dict, relevant_families: set) -> dict:
    relevance = [1 if family_by_id.get(pid) in relevant_families else 0 for pid in ranked_ids]
    total_relevant = sum(1 for fam in family_by_id.values() if fam in relevant_families)
    base_rate = total_relevant / len(family_by_id) if family_by_id else 0.0
    return ev.ranking_summary(relevance, base_rate, total_relevant)


def baseline_retrieval(baseline: dict, family_by_id: dict) -> dict:
    out = {}
    for key, analyses in baseline.items():
        ranked = sorted(analyses.values(), key=lambda a: (a["score"] is None, -(a["score"] or 0), a["company"]))
        out[key] = ranking_metrics([a["posting_id"] for a in ranked], family_by_id, RESUME_FOCUS.get(key, set()))
    return out


def discrimination(score_by_resume: dict[str, dict[str, float | None]], ids_by_family: dict) -> dict:
    """Paired comparison of the SE resume and the AI/ML resume on each posting family."""
    out = {}
    if "SE" not in score_by_resume or "AIML" not in score_by_resume:
        return out
    for family, ids in ids_by_family.items():
        se = [score_by_resume["SE"].get(pid) for pid in ids]
        aiml = [score_by_resume["AIML"].get(pid) for pid in ids]
        # Expected direction: the resume written for a family should win on that family.
        if family == "SE":
            comparison = ev.paired_comparison(se, aiml)
            comparison["expected"] = "SE resume scores higher than AI/ML resume"
        else:
            comparison = ev.paired_comparison(aiml, se)
            comparison["expected"] = "AI/ML resume scores higher than SE resume"
        out[f"{family}_postings"] = comparison
    return out


# --------------------------------------------------------------------------
# RAG
# --------------------------------------------------------------------------
def default_analyze(resume_text: str, posting_id: str) -> dict:
    from internalign_rag import analysis

    return analysis.analyze(resume_text, posting_id)


def default_match(resume_text: str, top: int) -> list[dict]:
    from internalign_rag import analysis, knowledge_base

    return knowledge_base.match_postings(analysis.resume_queries(resume_text), top_postings=top)


def run_rag(resumes, sample, analyze_fn, cache_path: Path, fresh: bool, log=print) -> list[dict]:
    cache = {}
    if cache_path.exists() and not fresh:
        for row in read_jsonl(cache_path):
            cache[(row["resume"], row["posting_id"])] = row
    rows = []
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(cache_path, "a" if not fresh else "w", encoding="utf-8")
    try:
        total = sum(len(ids) for ids in sample.values()) * len(resumes)
        done = 0
        for family, ids in sample.items():
            for posting_id in ids:
                for key, info in resumes.items():
                    done += 1
                    cached = cache.get((key, posting_id))
                    if cached:
                        rows.append(cached)
                        continue
                    started = time.perf_counter()
                    error = None
                    result = None
                    try:
                        result = analyze_fn(info["text"], posting_id)
                    except Exception as exc:  # a failed call is data too
                        error = f"{type(exc).__name__}: {exc}"
                    row = {
                        "resume": key,
                        "posting_id": posting_id,
                        "family": family,
                        "latency_s": time.perf_counter() - started,
                        "error": error,
                        "result": result,
                    }
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                    handle.flush()
                    rows.append(row)
                    log(f"  [{done}/{total}] {key} x {posting_id}: "
                        f"{'ERROR ' + error if error else 'score ' + str(result.get('score'))} "
                        f"({row['latency_s']:.1f}s)")
    finally:
        handle.close()
    return rows


def single_skill(requirement: str) -> str | None:
    """The one taxonomy skill a requirement names, or None if it names none or several."""
    from backend.skills import find_skills

    skills = find_skills(requirement)
    return skills[0] if len(skills) == 1 else None


def oracle_status(skill: str, resume_text: str) -> str:
    """Keyword oracle: 'present' (explicit mention), 'related' (only a related skill) or 'absent'."""
    from backend import gap_analysis

    status = gap_analysis.analyze_skill(skill, resume_text)["status"]
    return {SUPPORTED: "present", PARTIAL: "related", NOT_FOUND: "absent"}[status]


def requirement_rows(rag_rows, resumes, baseline, postings_by_id) -> list[dict]:
    """One flat row per requirement the RAG analysis returned."""
    out = []
    for row in rag_rows:
        result = row.get("result")
        if not result:
            continue
        resume_text = resumes[row["resume"]]["text"]
        base_by_skill = {r["requirement"]: r["status"]
                         for r in baseline.get(row["resume"], {}).get(row["posting_id"], {}).get("requirements", [])}
        for req in result.get("requirements", []):
            skill = single_skill(req["requirement"])
            out.append({
                "resume": row["resume"],
                "posting_id": row["posting_id"],
                "family": row["family"],
                "company": result.get("company", ""),
                "title": result.get("title", ""),
                "requirement": req["requirement"],
                "importance": req["importance"],
                "rag_status": req["status"],
                "evidence": " | ".join(req.get("resume_evidence", []))[:400],
                "n_evidence": len(req.get("resume_evidence", [])),
                "skill": skill or "",
                "oracle": oracle_status(skill, resume_text) if skill else "",
                "baseline_status": base_by_skill.get(skill, "") if skill else "",
            })
    return out


def faithfulness(rag_rows, resumes) -> dict:
    out = {}
    for key in resumes:
        rows = [r for r in rag_rows if r["resume"] == key and r.get("result")]
        kept = sum(len(q.get("resume_evidence", [])) for r in rows for q in r["result"]["requirements"])
        removed = sum(r["result"].get("unverified_quotes_removed", 0) for r in rows)
        listed = sum(len(r["result"]["requirements"]) for r in rows)
        ungrounded = sum(r["result"].get("ungrounded_requirements_removed", 0) for r in rows)
        # Post-guard audit, using the resume text and the evidence the user would actually see.
        shown_unverified = 0
        supported_no_evidence = 0
        for r in rows:
            for q in r["result"]["requirements"]:
                for line in q.get("resume_evidence", []):
                    if not ev.appears_in(line, resumes[key]["text"]):
                        shown_unverified += 1
                if q["status"] in (SUPPORTED, PARTIAL) and not q.get("resume_evidence"):
                    supported_no_evidence += 1
        out[key] = {
            "analyses": len(rows),
            "quotes_before_guard": kept + removed,
            "quote_support_rate": ev.rate(kept, kept + removed),
            "requirements_before_guard": listed + ungrounded,
            "requirement_grounding_rate": ev.rate(listed, listed + ungrounded),
            "unsupported_evidence_shown": shown_unverified,
            "supported_without_evidence": supported_no_evidence,
        }
    return out


def oracle_check(req_rows) -> dict:
    out = {}
    for key in sorted({r["resume"] for r in req_rows}):
        rows = [r for r in req_rows if r["resume"] == key and r["oracle"]]
        present = [r for r in rows if r["oracle"] == "present"]
        absent = [r for r in rows if r["oracle"] == "absent"]
        related = [r for r in rows if r["oracle"] == "related"]
        tp = sum(1 for r in present if r["rag_status"] == SUPPORTED)
        fp = sum(1 for r in absent if r["rag_status"] == SUPPORTED)
        out[key] = {
            "requirements_checked": len(rows),
            "present": len(present),
            "absent": len(absent),
            "related": len(related),
            "supported_recall_on_present": ev.rate(tp, len(present)),
            "unsupported_claim_rate_on_absent": ev.rate(fp, len(absent)),
            "partial_claim_rate_on_absent": ev.rate(sum(1 for r in absent if r["rag_status"] == PARTIAL), len(absent)),
            "supported_precision": ev.rate(tp, tp + fp),
            "related_status_mix": dict(Counter(r["rag_status"] for r in related)),
            "disputed": [
                {"posting_id": r["posting_id"], "requirement": r["requirement"], "evidence": r["evidence"]}
                for r in absent if r["rag_status"] == SUPPORTED
            ],
        }
    return out


def agreement_with_baseline(req_rows) -> dict:
    aligned = [r for r in req_rows if r["baseline_status"] in ev.STATUSES]
    rag = [r["rag_status"] for r in aligned]
    base = [r["baseline_status"] for r in aligned]
    result = ev.cohen_kappa(rag, base)
    result["confusion_rows_rag_cols_baseline"] = ev.confusion_matrix(rag, base)
    return result


def status_mix(rag_rows) -> dict:
    out = {}
    for key in sorted({r["resume"] for r in rag_rows}):
        for family in ("SE", "AIML"):
            counts = Counter()
            for r in rag_rows:
                if r["resume"] == key and r["family"] == family and r.get("result"):
                    for q in r["result"]["requirements"]:
                        if q["importance"] == "required":
                            counts[q["status"]] += 1
            total = sum(counts.values())
            out[f"{key}_resume_on_{family}_postings"] = {
                "required_requirements": total,
                **{s: (counts[s] / total if total else None) for s in ev.STATUSES},
            }
    return out


def rag_retrieval(resumes, family_by_id, match_fn, top=20) -> dict:
    out = {}
    for key, info in resumes.items():
        try:
            matches = match_fn(info["text"], top)
        except Exception as exc:
            out[key] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        ranked = [m["posting_id"] for m in matches]
        out[key] = ranking_metrics(ranked, family_by_id, RESUME_FOCUS.get(key, set()))
        out[key]["top5"] = [
            {"posting_id": m["posting_id"], "title": m.get("title", ""), "company": m.get("company", ""),
             "family": family_by_id.get(m["posting_id"], "?")}
            for m in matches[:5]
        ]
    return out


def efficiency(rag_rows, resumes) -> dict:
    latencies = [r["latency_s"] for r in rag_rows if not r["error"]]
    est_in, est_out = [], []
    for r in rag_rows:
        if r["error"] or not r.get("result"):
            continue
        resume_chars = min(resumes[r["resume"]]["chars"], 6000)
        # prompt template (~1.6k chars) + resume + up to 8 chunks of ~900 chars; 4 chars per token
        est_in.append((1600 + resume_chars + 900 * r["result"].get("retrieved_chunks", 8)) / 4)
        est_out.append(len(json.dumps(r["result"]["requirements"])) / 4)
    cost = [(i * PRICE_IN_PER_M + o * PRICE_OUT_PER_M) / 1_000_000 for i, o in zip(est_in, est_out)]
    return {
        "calls": len(rag_rows),
        "failed": sum(1 for r in rag_rows if r["error"]),
        "latency_s": ev.summarize(latencies),
        "estimated_input_tokens": ev.summarize(est_in),
        "estimated_output_tokens": ev.summarize(est_out),
        "estimated_cost_usd_per_analysis": ev.summarize(cost),
        "price_assumption_usd_per_million_tokens": {"input": PRICE_IN_PER_M, "output": PRICE_OUT_PER_M,
                                                   "note": "estimate from character counts; verify price and usage"},
    }


# --------------------------------------------------------------------------
# Labeling sheet and human-label scoring
# --------------------------------------------------------------------------
LABEL_COLUMNS = ["row_id", "resume", "posting_id", "company", "title", "requirement", "importance",
                 "rag_status", "evidence", "oracle", "human_status", "notes"]


def build_labeling_sheet(req_rows, per_resume: int = 25, seed: int = 152) -> list[dict]:
    """Rows for a person to label. Every disputed claim comes first, then unmapped 'Supported'
    claims, then a random mix of the rest."""
    rng = random.Random(seed)
    sheet = []
    for key in sorted({r["resume"] for r in req_rows}):
        rows = [r for r in req_rows if r["resume"] == key]
        disputed = [r for r in rows if r["oracle"] == "absent" and r["rag_status"] == SUPPORTED]
        unmapped_supported = [r for r in rows if not r["oracle"] and r["rag_status"] == SUPPORTED]
        rest = [r for r in rows if r not in disputed and r not in unmapped_supported]
        rng.shuffle(unmapped_supported)
        rng.shuffle(rest)
        chosen = (disputed + unmapped_supported[:8] + rest)[:per_resume]
        sheet.extend(chosen)
    out = []
    for i, r in enumerate(sheet, start=1):
        out.append({"row_id": i, "resume": r["resume"], "posting_id": r["posting_id"], "company": r["company"],
                    "title": r["title"], "requirement": r["requirement"], "importance": r["importance"],
                    "rag_status": r["rag_status"], "evidence": r["evidence"], "oracle": r["oracle"],
                    "human_status": "", "notes": ""})
    return out


def write_csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> None:
    columns = columns or (list(rows[0].keys()) if rows else [])
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def score_labels(path: Path) -> dict:
    with open(path, newline="", encoding="utf-8") as file:
        rows = [r for r in csv.DictReader(file) if r.get("human_status", "").strip()]
    truth = [r["human_status"].strip() for r in rows]
    pred = [r["rag_status"].strip() for r in rows]
    invalid = sorted({t for t in truth if t not in ev.STATUSES})
    if invalid:
        raise ValueError(f"human_status must be one of {list(ev.STATUSES)}; found {invalid}")
    metrics = ev.precision_recall_f1(truth, pred)
    metrics["kappa"] = ev.cohen_kappa(truth, pred)
    sup_pred = [t for t, p in zip(truth, pred) if p == SUPPORTED]
    metrics["supported_precision"] = ev.rate(sum(1 for t in sup_pred if t == SUPPORTED), len(sup_pred))
    metrics["labeled_rows"] = len(rows)
    return metrics


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
def _f(value, digits=2, pct=False):
    if value is None:
        return "n/a"
    return f"{value * 100:.0f}%" if pct else f"{value:.{digits}f}"


def render_summary(results: dict) -> str:
    lines = [f"# InternAlign evaluation ({results['generated_at'][:10]})", ""]
    corpus = results["corpus"]
    lines += [f"Corpus: {corpus['postings']} postings; families {corpus['families']}.", ""]
    lines += ["## Resumes", "| Resume | Characters | One-word-line ratio |", "|---|---|---|"]
    for key, info in results["resumes"].items():
        lines.append(f"| {key} | {info['chars']} | {_f(info['one_word_line_ratio'], pct=True)} |")
    lines += ["", "## 1. Discrimination (paired, same postings)", "",
              "| Method | Postings | n | Mean A | Mean B | Diff [95% CI] | Win rate | Sign-test p | Expected |",
              "|---|---|---|---|---|---|---|---|---|"]
    for method in ("baseline", "rag"):
        block = results.get(method, {})
        for name, c in block.get("discrimination", {}).items():
            if c.get("n", 0) == 0:
                continue
            lines.append(f"| {method} | {name} | {c['n']} | {_f(c['mean_a'], 1)} | {_f(c['mean_b'], 1)} | "
                         f"{_f(c['mean_diff'], 1)} [{_f(c['ci95'][0], 1)}, {_f(c['ci95'][1], 1)}] | "
                         f"{_f(c['win_rate_a'], pct=True)} | {_f(c['sign_test_p'], 3)} | {c['expected']} |")
    rag = results.get("rag")
    if rag:
        lines += ["", "## 2. Faithfulness (before and after the guard)", "",
                  "| Resume | Analyses | Quotes real before guard | Requirements in posting | Unsupported evidence shown | Supported w/o evidence |",
                  "|---|---|---|---|---|---|"]
        for key, f in rag["faithfulness"].items():
            lines.append(f"| {key} | {f['analyses']} | {_f(f['quote_support_rate']['rate'], pct=True)} "
                         f"({f['quote_support_rate']['k']}/{f['quote_support_rate']['n']}) | "
                         f"{_f(f['requirement_grounding_rate']['rate'], pct=True)} | "
                         f"{f['unsupported_evidence_shown']} | {f['supported_without_evidence']} |")
        lines += ["", "## 3. Check against the keyword oracle", "",
                  "| Resume | Checked | Supported recall (present) | Unsupported-claim rate (absent) | Supported precision |",
                  "|---|---|---|---|---|"]
        for key, o in rag["oracle_check"].items():
            lines.append(f"| {key} | {o['requirements_checked']} | {_f(o['supported_recall_on_present']['rate'], pct=True)} "
                         f"({o['supported_recall_on_present']['k']}/{o['supported_recall_on_present']['n']}) | "
                         f"{_f(o['unsupported_claim_rate_on_absent']['rate'], pct=True)} "
                         f"({o['unsupported_claim_rate_on_absent']['k']}/{o['unsupported_claim_rate_on_absent']['n']}) | "
                         f"{_f(o['supported_precision']['rate'], pct=True)} |")
        a = rag["agreement_with_baseline"]
        lines += ["", "## 4. Agreement with the rule-based baseline",
                  f"Cohen's kappa {_f(a['kappa'])}, raw agreement {_f(a['agreement'], pct=True)} on {a['n']} aligned requirements.", ""]
        lines += ["## 5. Required-requirement status mix", "", "| Resume on postings | Required reqs | Supported | Partial | Not found |", "|---|---|---|---|---|"]
        for name, m in rag["status_mix"].items():
            lines.append(f"| {name} | {m['required_requirements']} | {_f(m[SUPPORTED], pct=True)} | {_f(m[PARTIAL], pct=True)} | {_f(m[NOT_FOUND], pct=True)} |")
    lines += ["", "## 6. Retrieval (weak relevance label: role family from the title)", "",
              "| Method | Resume | P@5 | P@10 | nDCG@10 | MRR | Random P@5 | Lift@5 |", "|---|---|---|---|---|---|---|---|"]
    for method, block in (("rule-based ranking", results["baseline"].get("retrieval", {})),
                          ("RAG match", (rag or {}).get("retrieval", {}))):
        for key, m in block.items():
            if "error" in m:
                lines.append(f"| {method} | {key} | error: {m['error']} | | | | | |")
                continue
            lines.append(f"| {method} | {key} | {_f(m['precision@5'])} | {_f(m['precision@10'])} | {_f(m['ndcg@10'])} | "
                         f"{_f(m['mrr'])} | {_f(m['random_baseline@5'])} | {_f(m['lift@5'])} |")
    if rag:
        e = rag["efficiency"]
        lat = e["latency_s"]
        cost = e["estimated_cost_usd_per_analysis"]
        lines += ["", "## 7. Efficiency",
                  f"{e['calls']} calls, {e['failed']} failed. Latency mean {_f(lat.get('mean'), 1)} s, median {_f(lat.get('median'), 1)} s, "
                  f"p95 {_f(lat.get('p95'), 1)} s. Estimated cost per analysis {_f(cost.get('mean'), 4)} USD (estimate; verify).", ""]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def run_evaluation(args, analyze_fn=None, match_fn=None, log=print) -> dict:
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    parsed_path = Path(args.postings) if Path(args.postings).is_absolute() else ROOT / args.postings
    postings = read_jsonl(parsed_path)
    family_by_id = {p["id"]: ev.role_family(p.get("title", "")) for p in postings}
    postings_by_id = {p["id"]: p for p in postings}
    ids_by_family = {fam: [pid for pid, f in family_by_id.items() if f == fam] for fam in ("SE", "AIML")}

    resume_paths = dict(DEFAULT_RESUMES)
    for item in args.resume or []:
        key, _, path = item.partition("=")
        resume_paths[key] = path
    resumes = load_resumes(resume_paths)

    log("Rule-based baseline on every posting...")
    baseline = run_baseline(resumes, postings)
    base_scores = {k: {pid: a["score"] for pid, a in analyses.items()} for k, analyses in baseline.items()}
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "settings": {"n_per_family": args.n_per_family, "seed": args.seed, "skip_rag": args.skip_rag},
        "corpus": {"postings": len(postings), "families": dict(Counter(family_by_id.values()))},
        "resumes": {k: {kk: vv for kk, vv in v.items() if kk != "text"} for k, v in resumes.items()},
        "baseline": {
            "mean_score": {k: {fam: ev.summarize([s for pid, s in sc.items() if family_by_id[pid] == fam])
                               for fam in ("SE", "AIML")} for k, sc in base_scores.items()},
            "discrimination": discrimination(base_scores, ids_by_family),
            "retrieval": baseline_retrieval(baseline, family_by_id),
        },
    }

    if not args.skip_rag:
        analyze_fn = analyze_fn or default_analyze
        match_fn = match_fn or default_match
        sample = sample_postings(postings, args.n_per_family, args.seed)
        log(f"RAG analysis on {sum(len(v) for v in sample.values())} postings x {len(resumes)} resumes...")
        rag_rows = run_rag(resumes, sample, analyze_fn, out_dir / "rag_pairs.jsonl", args.fresh, log)
        ok = [r for r in rag_rows if not r["error"] and r.get("result")]
        rag_scores = defaultdict(dict)
        for r in ok:
            rag_scores[r["resume"]][r["posting_id"]] = r["result"].get("score")
        sampled_ids = {fam: ids for fam, ids in sample.items()}
        req_rows = requirement_rows(ok, resumes, baseline, postings_by_id)
        results["rag"] = {
            "model": next((r["result"].get("model") for r in ok), None),
            "sample": {fam: len(ids) for fam, ids in sampled_ids.items()},
            "mean_score": {k: {fam: ev.summarize([rag_scores[k].get(pid) for pid in sampled_ids[fam]])
                               for fam in ("SE", "AIML")} for k in resumes},
            "discrimination": discrimination(rag_scores, sampled_ids),
            "baseline_on_same_sample": discrimination(base_scores, sampled_ids),
            "faithfulness": faithfulness(ok, resumes),
            "oracle_check": oracle_check(req_rows),
            "agreement_with_baseline": agreement_with_baseline(req_rows),
            "status_mix": status_mix(ok),
            "retrieval": rag_retrieval(resumes, family_by_id, match_fn),
            "efficiency": efficiency(rag_rows, resumes),
        }
        write_csv(out_dir / "rag_requirements.csv", req_rows)
        write_csv(out_dir / "labeling_sheet.csv", build_labeling_sheet(req_rows), LABEL_COLUMNS)

    (out_dir / "eval_results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = render_summary(results)
    (out_dir / "eval_summary.md").write_text(summary, encoding="utf-8")
    log(f"\nWrote results to {out_dir}\n")
    log(summary)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate the InternAlign analysis modes.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the evaluation")
    run.add_argument("--postings", default="data/parsed_postings.jsonl")
    run.add_argument("--resume", action="append", help="KEY=path to override a resume, e.g. SE=data/resume/x.pdf")
    run.add_argument("--n-per-family", type=int, default=15, help="postings sampled per role family for the RAG run")
    run.add_argument("--seed", type=int, default=152)
    run.add_argument("--out", default="data/eval")
    run.add_argument("--skip-rag", action="store_true", help="baseline only (no index, no API key)")
    run.add_argument("--fresh", action="store_true", help="ignore the cache and call the model again")
    labels = sub.add_parser("score-labels", help="score a filled labeling sheet")
    labels.add_argument("sheet")
    args = parser.parse_args(argv)

    if args.command == "run":
        run_evaluation(args)
    else:
        metrics = score_labels(Path(args.sheet))
        print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
