"""
Collect raw software-internship postings from the public Greenhouse, Lever and
Ashby job-board APIs for the companies listed in data/companies.csv.

Pipeline: fetch -> keep software internships -> drop thin postings -> drop
exact and near duplicates -> balance across companies -> write JSONL + report.

Usage:
    python fetch_postings.py
    python fetch_postings.py --target 350 --max-per-company 8
"""
import argparse
import csv
import hashlib
import html
import json
import random
import re
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
USER_AGENT = "Mozilla/5.0 (CS152 InternAlign class project)"

# Title filters
INTERN = re.compile(r"\b(intern|interns|internship|co-?op)\b", re.I)
SOFTWARE = re.compile(
    r"software|\bswe\b|developer|programm|machine learning|\bml\b|\bai\b|"
    r"data (science|engineer)|full.?stack|back-?end|front-?end|computer vision|"
    r"\bsre\b|devops|firmware|embedded|platform engineer|infrastructure engineer|"
    r"member of technical staff|forward deployed|\bsde\b|\bios\b|android|\bc\+\+",
    re.I,
)
EXCLUDE = re.compile(
    r"high school|manager|business|sales|marketing|finance|legal|recruit|"
    r"design(er)?\b|analyst|quant|trader|mechanical|electrical|manufactur|"
    r"propulsion|structur|civil|supply|rf |thermal|avionics|process engineer|"
    r"facilit|consulting|controls|hardware|fpga",
    re.I,
)

# Content sufficiency: does the text describe a SWE role?
TECH_TERMS = re.compile(
    r"python|java\b|javascript|typescript|c\+\+|\bc#|golang|\bgo\b|rust|kotlin|swift|"
    r"\bsql\b|react|node\.?js|django|flask|spring|aws|azure|gcp|docker|kubernetes|"
    r"linux|git\b|rest\b|api|pytorch|tensorflow|spark|kafka|postgres|mongodb|"
    r"algorithm|data structure",
    re.I,
)
REQUIREMENTS_HEADER = re.compile(
    r"qualifications|requirements|what you.?ll need|what we.?re looking for|"
    r"who you are|skills|you have|minimum|preferred",
    re.I,
)
MIN_WORDS = 150

# HTML -> text
class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(raw_html: str) -> str:
    parser = _TextExtractor()
    parser.feed(raw_html or "")
    text = "".join(parser.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


# Fetching
def get_json(url: str, retries: int = 2):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except Exception:
            if attempt == retries:
                raise
            time.sleep(2 * (attempt + 1))

def fetch_jobs(ats: str, slug: str) -> list[dict]:
    """Return normalized postings: title, location, url, posting_id, raw_html."""
    if ats == "greenhouse":
        data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
        jobs = []
        for j in data["jobs"]:
            jobs.append(
                {
                    "posting_id": str(j["id"]),
                    "title": j["title"],
                    "location": (j.get("location") or {}).get("name", ""),
                    "url": j["absolute_url"],
                    # Greenhouse returns the description as HTML-escaped HTML.
                    "raw_html": html.unescape(j.get("content", "")),
                }
            )
        return jobs
    if ats == "lever":
        data = get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        jobs = []
        for j in data:
            sections = ""
            for section in j.get("lists", []):
                sections += f"<h3>{section.get('text', '')}</h3>{section.get('content', '')}"
            jobs.append(
                {
                    "posting_id": j["id"],
                    "title": j["text"],
                    "location": (j.get("categories") or {}).get("location", ""),
                    "url": j["hostedUrl"],
                    "raw_html": j.get("description", "") + sections + j.get("additional", ""),
                }
            )
        return jobs
    if ats == "ashby":
        data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
        jobs = []
        for j in data["jobs"]:
            jobs.append(
                {
                    "posting_id": j["id"],
                    "title": j["title"],
                    "location": j.get("location", ""),
                    "url": j["jobUrl"],
                    "raw_html": j.get("descriptionHtml", ""),
                }
            )
        return jobs
    raise ValueError(f"Unknown ATS: {ats}")


# Quality, dedupe, balance
def sufficiency_problem(text: str) -> str | None:
    """Return why a posting is too thin to label, or None if it is fine."""
    if len(text.split()) < MIN_WORDS:
        return "too_short"
    if not TECH_TERMS.search(text) and not REQUIREMENTS_HEADER.search(text):
        return "no_tech_or_requirements"
    return None


def shingles(text: str, n: int = 5) -> set:
    words = re.findall(r"[a-z0-9+#.]+", text.lower())
    result = set()
    for i in range(max(len(words) - n + 1, 1)):
        result.add(" ".join(words[i : i + n]))
    return result


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def dedupe(postings: list[dict], threshold: float) -> tuple[list[dict], Counter]:
    """Drop exact duplicates globally and near duplicates within a company
    (the same role posted once per city)."""
    dropped = Counter()
    seen_hashes = set()
    kept_by_company: dict[str, list[tuple[dict, set]]] = {}
    kept = []
    for posting in postings:
        digest = hashlib.sha256(" ".join(posting["text"].lower().split()).encode()).hexdigest()
        if digest in seen_hashes:
            dropped["exact_duplicate"] += 1
            continue
        seen_hashes.add(digest)
        sig = shingles(posting["text"])
        siblings = kept_by_company.setdefault(posting["slug"], [])
        is_near_duplicate = False
        for _, other in siblings:
            if jaccard(sig, other) >= threshold:
                is_near_duplicate = True
                break
        if is_near_duplicate:
            dropped["near_duplicate"] += 1
            continue
        siblings.append((posting, sig))
        kept.append(posting)
    return kept, dropped


def balance(postings: list[dict], target: int, max_per_company: int, seed: int) -> list[dict]:
    """Round-robin across companies so no single company dominates.
    Each round takes at most one posting per company, until the target or the
    per-company cap is reached."""
    rng = random.Random(seed)
    queues: dict[str, list[dict]] = {}
    for posting in postings:
        queues.setdefault(posting["slug"], []).append(posting)
    for queue in queues.values():
        rng.shuffle(queue)
    order = sorted(queues)
    rng.shuffle(order)

    selected = []
    taken = Counter()
    progress = True
    while len(selected) < target and progress:
        progress = False
        for slug in order:
            if len(selected) >= target:
                break
            if queues[slug] and (max_per_company <= 0 or taken[slug] < max_per_company):
                selected.append(queues[slug].pop())
                taken[slug] += 1
                progress = True
    return selected


def build_report(selected: list[dict], pool_size: int, drops: Counter, args) -> dict:
    per_company = Counter()
    per_ats = Counter()
    for posting in selected:
        per_company[posting["company"]] += 1
        per_ats[posting["ats"]] += 1
    top_company, top_count = per_company.most_common(1)[0] if per_company else ("", 0)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "settings": {"target": args.target, "max_per_company": args.max_per_company,
                     "near_duplicate_threshold": args.near_dup, "seed": args.seed},
        "pool_after_cleaning": pool_size,
        "selected": len(selected),
        "companies_represented": len(per_company),
        "largest_company": {"name": top_company, "count": top_count,
                            "share": round(top_count / len(selected), 3) if selected else 0},
        "per_ats": dict(per_ats),
        "per_company": dict(per_company.most_common()),
        "dropped": dict(drops),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--companies", default=str(DATA_DIR / "companies.csv"))
    parser.add_argument("--output", default=str(DATA_DIR / "raw_postings.jsonl"))
    parser.add_argument("--report", default=str(DATA_DIR / "raw_postings_report.json"))
    parser.add_argument("--target", type=int, default=350, help="postings to keep after balancing")
    parser.add_argument("--max-per-company", type=int, default=8, help="0 disables the cap")
    parser.add_argument("--near-dup", type=float, default=0.8, help="Jaccard threshold for near duplicates")
    parser.add_argument("--delay", type=float, default=0.5, help="seconds between company requests")
    parser.add_argument("--seed", type=int, default=152)
    args = parser.parse_args()

    with open(args.companies, newline="") as f:
        companies = list(csv.DictReader(f))

    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    drops = Counter()
    pool = []

    for i, row in enumerate(companies, 1):
        ats, slug, company = row["ats"], row["slug"], row["company"]
        try:
            jobs = fetch_jobs(ats, slug)
        except Exception as error:
            print(f"[{i}/{len(companies)}] {ats}/{slug}: FAILED ({error})")
            drops["fetch_failed"] += 1
            continue

        matched = 0
        for job in jobs:
            title = job["title"]
            if not (INTERN.search(title) and SOFTWARE.search(title) and not EXCLUDE.search(title)):
                continue
            text = html_to_text(job["raw_html"])
            problem = sufficiency_problem(text)
            if problem:
                drops[problem] += 1
                continue
            matched += 1
            pool.append({
                "id": f"{ats}:{slug}:{job['posting_id']}",
                "ats": ats, "slug": slug, "company": company,
                "title": title.strip(), "location": job["location"], "url": job["url"],
                "fetched_at": fetched_at, "text": text, "raw_html": job["raw_html"],
            })
        print(f"[{i}/{len(companies)}] {ats}/{slug}: {matched} usable")
        time.sleep(args.delay)

    deduped, dedupe_drops = dedupe(pool, args.near_dup)
    drops.update(dedupe_drops)
    selected = balance(deduped, args.target, args.max_per_company, args.seed)
    drops["cut_by_balancing"] = len(deduped) - len(selected)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        for posting in selected:
            f.write(json.dumps(posting, ensure_ascii=False) + "\n")

    report = build_report(selected, len(deduped), drops, args)
    with open(args.report, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nWrote {len(selected)} postings -> {args.output}")
    print(f"Pool after cleaning/dedupe: {len(deduped)} | companies represented: "
          f"{report['companies_represented']} | largest company: "
          f"{report['largest_company']['name']} ({report['largest_company']['share']:.0%})")
    print(f"By ATS: {report['per_ats']}")
    print(f"Dropped: {report['dropped']}")
    if len(selected) < args.target:
        print(f"WARNING: only {len(selected)} of the {args.target} target postings are available. "
              f"Add more companies to {args.companies} or raise --max-per-company.")


if __name__ == "__main__":
    main()
