# InternAlign evaluation (2026-10-23)

Corpus: 322 postings; families {'SE': 221, 'AIML': 67, 'hybrid': 10, 'other': 24}.

## Resumes
| Resume | Characters | One-word-line ratio |
|---|---|---|
| SE | 3784 | 4% |
| AIML | 4202 | 2% |

## 1. Discrimination (paired, same postings)

| Method | Postings | n | Mean A | Mean B | Diff [95% CI] | Win rate | Sign-test p | Expected |
|---|---|---|---|---|---|---|---|---|
| baseline | SE_postings | 216 | 54.4 | 65.4 | -11.0 [-14.2, -7.8] | 34% | 0.000 | SE resume scores higher than AI/ML resume |
| baseline | AIML_postings | 67 | 88.5 | 64.7 | 23.9 [19.8, 28.2] | 93% | 0.000 | AI/ML resume scores higher than SE resume |
| rag | SE_postings | 15 | 53.1 | 48.5 | 4.6 [-6.7, 16.9] | 60% | 0.581 | SE resume scores higher than AI/ML resume |
| rag | AIML_postings | 15 | 51.1 | 44.7 | 6.5 [-0.7, 13.6] | 63% | 0.388 | AI/ML resume scores higher than SE resume |

## 2. Faithfulness (before and after the guard)

| Resume | Analyses | Quotes real before guard | Requirements in posting | Unsupported evidence shown | Supported w/o evidence |
|---|---|---|---|---|---|
| SE | 30 | 93% (201/215) | 97% | 0 | 0 |
| AIML | 30 | 95% (202/212) | 97% | 0 | 0 |

## 3. Check against the keyword oracle

| Resume | Checked | Supported recall (present) | Unsupported-claim rate (absent) | Supported precision |
|---|---|---|---|---|
| AIML | 107 | 81% (68/84) | 14% (2/14) | 97% |
| SE | 101 | 98% (53/54) | 4% (1/27) | 98% |

## 4. Agreement with the rule-based baseline
Cohen's kappa 0.54, raw agreement 77% on 206 aligned requirements.

## 5. Required-requirement status mix

| Resume on postings | Required reqs | Supported | Partial | Not found |
|---|---|---|---|---|
| AIML_resume_on_SE_postings | 78 | 60% | 1% | 38% |
| AIML_resume_on_AIML_postings | 66 | 53% | 9% | 38% |
| SE_resume_on_SE_postings | 69 | 49% | 3% | 48% |
| SE_resume_on_AIML_postings | 55 | 56% | 9% | 35% |

## 6. Retrieval (weak relevance label: role family from the title)

| Method | Resume | P@5 | P@10 | nDCG@10 | MRR | Random P@5 | Lift@5 |
|---|---|---|---|---|---|---|---|
| rule-based ranking | SE | 0.60 | 0.60 | 0.49 | 0.33 | 0.72 | 0.84 |
| rule-based ranking | AIML | 0.20 | 0.40 | 0.30 | 0.25 | 0.24 | 0.84 |
| RAG match | SE | 0.40 | 0.60 | 0.61 | 1.00 | 0.72 | 0.56 |
| RAG match | AIML | 0.60 | 0.70 | 0.75 | 1.00 | 0.24 | 2.51 |

## 7. Efficiency
60 calls, 0 failed. Latency mean 7.1 s, median 7.1 s, p95 9.2 s. Estimated cost per analysis 0.0012 USD (estimate; verify).

