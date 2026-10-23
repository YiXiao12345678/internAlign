"""
Evaluation metrics for the InternAlign analysis (rule-based baseline and RAG).

Metric families (all standard in information retrieval / classification / RAG work):

  * Classification: per-class precision, recall, F1, macro-F1, accuracy,
    Cohen's kappa (agreement between two labelers, corrected for chance).
  * Retrieval / ranking: Precision@k, nDCG@k (binary relevance), reciprocal
    rank, and lift over the random baseline.
  * Paired comparison: mean difference with a bootstrap confidence interval,
    win rate (the probability that A beats B, equal to the ROC-AUC of the
    pairwise comparison, ties count half), an exact sign test and Cohen's d_z.
  * Faithfulness (groundedness): the share of generated evidence that can be
    found in the source document. This is the deterministic analogue of the
    "faithfulness" metric used by RAG evaluation toolkits.
"""
from __future__ import annotations

import math
import random
import re
import statistics

STATUSES = ("Supported", "Partially supported", "Not found")

# Role families, a weak label taken from the posting title
_ML_TITLE = re.compile(
    r"machine learning|\bml\b|\bai\b|\ba\.i\.|artificial|deep learning|computer vision|\bnlp\b|"
    r"data scien|applied scien|research|\bllm|generative|perception|autonomy",
    re.IGNORECASE,
)
_SE_TITLE = re.compile(
    r"software|\bswe\b|developer|back-?end|front-?end|full.?stack|platform|infrastructure|"
    r"mobile|\bios\b|android|devops|\bsre\b|\bsde\b|\bweb\b|firmware|embedded|systems",
    re.IGNORECASE,
)


def role_family(title: str) -> str:
    """'SE', 'AIML', 'hybrid' (both signals in the title) or 'other'."""
    title = title or ""
    ml = bool(_ML_TITLE.search(title))
    se = bool(_SE_TITLE.search(title))
    if ml and se:
        return "hybrid"
    if ml:
        return "AIML"
    if se:
        return "SE"
    return "other"


# Text helpers
def normalize(text: str) -> str:
    """Lowercase and collapse everything except letters, digits, + and # to single spaces."""
    return re.sub(r"[^a-z0-9+#]+", " ", (text or "").lower()).strip()


def appears_in(quote: str, source: str) -> bool:
    needle = normalize(quote)
    return len(needle) >= 3 and needle in normalize(source)


def one_word_line_ratio(text: str) -> float:
    """Share of non-empty lines with at most one word. High values mean the PDF text came out
    fragmented, which makes evidence quotes and section detection unreliable."""
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return 0.0
    return sum(1 for line in lines if len(line.split()) <= 1) / len(lines)


# Classification metrics
def confusion_matrix(y_true, y_pred, labels=STATUSES) -> dict:
    matrix = {t: {p: 0 for p in labels} for t in labels}
    for truth, pred in zip(y_true, y_pred):
        if truth in matrix and pred in matrix[truth]:
            matrix[truth][pred] += 1
    return matrix


def precision_recall_f1(y_true, y_pred, labels=STATUSES) -> dict:
    """Per-class precision / recall / F1 plus macro-F1 and accuracy. Undefined values are None."""
    matrix = confusion_matrix(y_true, y_pred, labels)
    per_class = {}
    f1_values = []
    for label in labels:
        tp = matrix[label][label]
        fp = sum(matrix[other][label] for other in labels if other != label)
        fn = sum(matrix[label][other] for other in labels if other != label)
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        if precision is None or recall is None:
            f1 = None
        elif precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
        if f1 is not None and (tp + fn) > 0:
            f1_values.append(f1)
    total = sum(sum(row.values()) for row in matrix.values())
    correct = sum(matrix[label][label] for label in labels)
    return {
        "per_class": per_class,
        "macro_f1": sum(f1_values) / len(f1_values) if f1_values else None,
        "accuracy": correct / total if total else None,
        "n": total,
        "confusion": matrix,
    }


def cohen_kappa(a, b, labels=STATUSES) -> dict:
    """Cohen's kappa for two labelers over the same items."""
    pairs = [(x, y) for x, y in zip(a, b) if x in labels and y in labels]
    n = len(pairs)
    if n == 0:
        return {"kappa": None, "agreement": None, "n": 0}
    observed = sum(1 for x, y in pairs if x == y) / n
    expected = 0.0
    for label in labels:
        pa = sum(1 for x, _ in pairs if x == label) / n
        pb = sum(1 for _, y in pairs if y == label) / n
        expected += pa * pb
    if expected >= 1.0:
        kappa = 1.0 if observed >= 1.0 else 0.0
    else:
        kappa = (observed - expected) / (1 - expected)
    return {"kappa": kappa, "agreement": observed, "n": n}


def wilson_interval(successes: int, n: int, z: float = 1.96):
    """95% Wilson score interval for a proportion (well behaved for small n and for 0 or 100%)."""
    if n == 0:
        return (None, None)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(successes: int, n: int) -> dict:
    low, high = wilson_interval(successes, n)
    return {"k": successes, "n": n, "rate": (successes / n) if n else None, "ci95": [low, high]}


# --------------------------------------------------------------------------
# Paired comparison
# --------------------------------------------------------------------------
def exact_sign_test(wins: int, losses: int) -> float | None:
    """Two-sided exact binomial (sign) test p-value; ties are excluded by the caller."""
    n = wins + losses
    if n == 0:
        return None
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def bootstrap_mean_ci(values, n_boot: int = 2000, seed: int = 152, alpha: float = 0.05):
    values = list(values)
    if not values:
        return (None, None)
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(len(values))] for _ in values]
        means.append(sum(sample) / len(sample))
    means.sort()
    low = means[int((alpha / 2) * n_boot)]
    high = means[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return (low, high)


def paired_comparison(scores_a, scores_b, seed: int = 152) -> dict:
    """Compare A with B on the same items. Items where either score is None are dropped."""
    pairs = [(a, b) for a, b in zip(scores_a, scores_b) if a is not None and b is not None]
    n = len(pairs)
    if n == 0:
        return {"n": 0}
    diffs = [a - b for a, b in pairs]
    wins = sum(1 for d in diffs if d > 0)
    losses = sum(1 for d in diffs if d < 0)
    ties = n - wins - losses
    mean_diff = sum(diffs) / n
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    low, high = bootstrap_mean_ci(diffs, seed=seed)
    return {
        "n": n,
        "mean_a": sum(a for a, _ in pairs) / n,
        "mean_b": sum(b for _, b in pairs) / n,
        "mean_diff": mean_diff,
        "ci95": [low, high],
        "win_rate_a": (wins + 0.5 * ties) / n,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "sign_test_p": exact_sign_test(wins, losses),
        "cohens_dz": (mean_diff / sd) if sd > 0 else None,
    }


# Ranking metrics (binary relevance)
def precision_at_k(relevance: list[int], k: int) -> float:
    if k <= 0:
        return 0.0
    return sum(relevance[:k]) / k


def dcg_at_k(relevance: list[int], k: int) -> float:
    return sum(rel / math.log2(rank + 2) for rank, rel in enumerate(relevance[:k]))


def ndcg_at_k(relevance: list[int], k: int, total_relevant: int | None = None) -> float | None:
    """nDCG@k. `total_relevant` is the number of relevant items in the whole corpus; when it is
    omitted the ideal ranking is built from the relevant items inside the list."""
    if total_relevant is None:
        total_relevant = sum(relevance)
    ideal = dcg_at_k([1] * min(total_relevant, k), k)
    if ideal == 0:
        return None
    return dcg_at_k(relevance, k) / ideal


def reciprocal_rank(relevance: list[int]) -> float:
    for rank, rel in enumerate(relevance, start=1):
        if rel:
            return 1.0 / rank
    return 0.0


def ranking_summary(relevance: list[int], base_rate: float, total_relevant: int) -> dict:
    p5 = precision_at_k(relevance, 5)
    return {
        "precision@5": p5,
        "precision@10": precision_at_k(relevance, 10),
        "ndcg@10": ndcg_at_k(relevance, 10, total_relevant),
        "mrr": reciprocal_rank(relevance),
        "random_baseline@5": base_rate,
        "lift@5": (p5 / base_rate) if base_rate else None,
    }


# Descriptive statistics
def percentile(values, q: float):
    values = sorted(values)
    if not values:
        return None
    index = min(len(values) - 1, max(0, math.ceil(q * len(values)) - 1))
    return values[index]


def summarize(values) -> dict:
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": sum(values) / len(values),
        "median": statistics.median(values),
        "p95": percentile(values, 0.95),
        "min": min(values),
        "max": max(values),
    }
