# InternAlign

AI-powered resume analysis and tailoring assistant for software internship applications
(CS 152 project). See the project proposal for the full scope.

## What works today

| Area | Status |
| --- | --- |
| Accounts (sign up / log in, JWT) | Working |
| Resume upload (PDF, DOCX, TXT), original file kept untouched | Working |
| Posting parser (required vs. preferred skills, responsibilities) | Rule-based baseline |
| Gap analysis: Supported / Partially supported / Not found, with verbatim resume evidence | Rule-based baseline |
| Clarification questions for every gap (nothing is invented) | Template-based |
| Job ranking by fit (optional Component 3) | Working on top of gap analysis |
| Dashboard UI wired to the API | Working |
| DistilBERT extractor, RAG + GPT-4o suggestions, side-by-side edit/accept, DOCX/PDF export | Not started |

The rule-based parser and analysis are the **baseline** the fine-tuned extractor and the
GPT-4o pipeline will be compared against.

## Run it

Backend (from the project root):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then set INTERNALIGN_SECRET_KEY
uvicorn backend.api:app --reload
```

Frontend:

```bash
cd frontend-web
npm install
npm run dev                   # http://localhost:5173
```

The frontend talks to `http://127.0.0.1:8000` by default; override with `VITE_API_URL`.

## Data pipeline

```bash
python fetch_postings.py                  # collect raw postings -> data/raw_postings.jsonl
python -m backend.job_parser              # parse -> data/parsed_postings.jsonl
python -m backend.gap_analysis --resume path/to/resume.pdf --rank     # rank all postings
python -m backend.gap_analysis --resume path/to/resume.pdf --posting-index 3
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Layout

```
backend/
  api.py              FastAPI app and routes
  auth_api.py         signup / login / current-user dependency
  skills.py           skill taxonomy, aliases, related skills, matcher
  job_parser.py       raw posting -> structured record
  resume_parser.py    PDF/DOCX/TXT -> text, section detection
  gap_analysis.py     requirement-vs-resume matching, scoring, ranking
frontend-web/src/
  App.jsx             login gate and session handling
  Dashboard.jsx       overview / job matches / my resume
  components/         JobCard, AnalysisPanel, ResumeView
  api.js              fetch wrapper
```
