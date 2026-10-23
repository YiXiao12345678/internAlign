# Evaluating the analysis (rule-based baseline vs. RAG)

`ai-workflow/evaluate.py` measures both analysis modes on the two sample resumes in
`data/resume/` (`yuji_n_resume_SE.pdf` written for software-engineering roles and
`yuji_n_resume.pdf` written for AI/ML roles) against the collected postings.

## Run it

From the project root, virtual environment active, `OPENAI_API_KEY` in `.env`, index built
(`python ai-workflow/cli.py index`):

```bash
python ai-workflow/evaluate.py run                    # 30 postings x 2 resumes = 60 GPT-4o-mini calls (a few minutes, well under $1)
python ai-workflow/evaluate.py run --skip-rag         # baseline only; no API key or index needed
python ai-workflow/evaluate.py run --n-per-family 25  # bigger sample
python ai-workflow/evaluate.py score-labels data/eval/labeling_sheet.csv   # after filling human_status
pytest ai-workflow/tests/test_evaluation.py           # offline tests for the metrics and the runner
```

Results land in `data/eval/`: `eval_summary.md` (read this first), `eval_results.json`,
`rag_requirements.csv` (every requirement the model returned), `labeling_sheet.csv`
(rows for a person to label) and `rag_pairs.jsonl` (cache; an interrupted run resumes,
`--fresh` starts over). The sample is stratified by role family and seeded (152), so reruns
use the same postings.

## What is measured, and why

| # | Question | Metric (standard name) |
|---|---|---|
| 1 | Does the score depend on how well the resume fits the posting? | Paired comparison of the two resumes on the same postings: mean difference with bootstrap 95% CI, win rate (= pairwise ROC-AUC, ties count half), exact sign test |
| 2 | Is the evidence real? | Faithfulness: share of quotes that exist in the resume before the guard; share of requirements that exist in the posting; a post-guard audit (unsupported evidence shown, "Supported" without evidence). The target from the proposal is 0 shown |
| 3 | Does RAG claim skills the resume never mentions? | Keyword-oracle check on requirements that map to one taxonomy skill: recall of "Supported" when the skill is present, unsupported-claim rate when it is absent, precision of "Supported" |
| 4 | Do the two modes agree? | Cohen's kappa and raw agreement on the same requirements |
| 5 | Does matching surface the right postings? | Precision@5, Precision@10, nDCG@10, MRR, lift over random (retrieval metrics from the proposal) |
| 6 | Is it practical? | Latency (mean, median, p95), estimated tokens and cost per analysis |
| 7 | How accurate is it against a person? | Precision, recall, F1 per status, macro-F1, kappa, and Wilson 95% CIs, from `labeling_sheet.csv` |

## How to read the results (limits)

* **Role-family labels are weak.** Relevance for retrieval and the expected direction in (1)
  come from the posting title (`SE`, `AIML`, `hybrid`, `other`). A "software engineer" posting
  can legitimately ask for ML, and the SE resume lacks C/C++ while about half of the SE postings
  request it, so a resume written "for SE" does not have to beat the AI/ML resume on every
  SE posting. Treat (1) as a test of the system's behaviour, not a pass/fail of the resumes.
* **The keyword oracle is a silver standard.** "Absent" means the taxonomy finds no mention
  of the skill or a related skill in the resume. A "Supported" claim on an absent skill is
  either a real over-claim or a synonym the taxonomy misses. Every such row goes into
  `labeling_sheet.csv` first, so a person decides. The baseline is not scored by this check
  because it is the oracle (circular).
* **Counts of removed quotes are a lower bound.** The guard counts removed quotes only for
  requirements that survive the posting check and are not duplicates, so the true rate of
  invented quotes is at least what is reported.
* **Small samples.** With 15 postings per family, read the confidence intervals, not the
  point estimates. Increase `--n-per-family` before drawing conclusions.
* **Cost is an estimate** from character counts and list prices in `evaluate.py`; check the
  OpenAI usage page for actual spend.
