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
| RAG gap analysis (`ai-workflow/`): FAISS index of postings + GPT-4o-mini, every quote verified against the resume | Working (switch it on in the dashboard) |
| DistilBERT extractor, answering clarifying questions, side-by-side edit/accept, DOCX/PDF export | Not started |

The rule-based parser and analysis are the **baseline** the fine-tuned extractor and the
RAG pipeline are compared against. The dashboard has a Rule-based / AI (RAG) switch so you can see both.

## Run the whole project

### 1. Install once

| You need | Why | Tested with |
| --- | --- | --- |
| Python 3.12 | backend and RAG | 3.12.10 |
| Node.js + npm | React dashboard | Node 24, npm 11 |
| An OpenAI API key with credit | GPT-4o-mini answers (the key page: https://platform.openai.com/api-keys, credit under Billing) | |
| ~2 GB free disk | PyTorch and the embedding model | |

There are **two** Python requirements files. Install both, into one virtual environment:

| File | What it installs |
| --- | --- |
| `requirements.txt` (root) | the web app: FastAPI, SQLAlchemy, accounts, resume parsing, `certifi` for the collector |
| `ai-workflow/requirements.txt` | the RAG system: LangChain, FAISS, sentence-transformers (pulls in PyTorch, so it is large), `langchain-openai` |
| `requirements-dev.txt` (optional) | `pytest` and `httpx`, only for running tests |

```bash
python3 -m venv .venv
source .venv/bin/activate                      # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r ai-workflow/requirements.txt

cd frontend-web && npm install && cd ..
```

Create your settings file and paste your OpenAI key:

```bash
cp .env.example .env
```

Then edit `.env`:

```
INTERNALIGN_SECRET_KEY=<any long random string>
OPENAI_API_KEY=<your key>
```

Generate the secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
`.env` is git-ignored; never commit it.

### 2. Prepare the data (once, and again whenever the postings change)

`data/*.jsonl` and the index are git-ignored, so every teammate builds them locally.

```bash
python fetch_postings.py                   # collect postings  -> data/raw_postings.jsonl  (a few minutes)
python -m backend.job_parser               # rule-based parse  -> data/parsed_postings.jsonl
python ai-workflow/cli.py index            # embed + save FAISS -> data/faiss_index  (downloads a ~90 MB model the first time)
```

The dashboard's job list and the rule-based analysis read `parsed_postings.jsonl`. The AI
analysis reads the FAISS index. Both come from `raw_postings.jsonl`, so run all three.

### 3. Start the app (two terminals, both from the project root)

```bash
# Terminal 1: API on http://127.0.0.1:8000  (virtual environment active)
uvicorn backend.api:app --reload

# Terminal 2: dashboard on http://localhost:5173
cd frontend-web && npm run dev
```

Open http://localhost:5173. The dashboard talks to `http://127.0.0.1:8000` by default;
override with `VITE_API_URL`. Restart the API after rebuilding the index.

### 4. Try it in the GUI

1. Sign up and log in.
2. Upload a resume (PDF, DOCX or TXT, up to 5 MB). Your original file is kept untouched.
3. Open **Job matches** and pick a posting. You get the rule-based analysis first.
4. Click **AI (RAG)** above the analysis. It retrieves the posting from the index, asks
   GPT-4o-mini, and shows the same layout. Expect a few seconds. The line "AI analysis by
   gpt-4o-mini-..." confirms the model, and a note appears if any quote or requirement was
   thrown out because it was not really in your resume or the posting.

No browser? The same pipeline runs from the command line:

```bash
python ai-workflow/cli.py status
python ai-workflow/cli.py match   --resume path/to/resume.pdf
python ai-workflow/cli.py analyze --resume path/to/resume.pdf --posting-id "greenhouse:databricks:6865687002"
```

### Using a different model

Set `RAG_LLM_PROVIDER` in `.env` to `openai` (default), `huggingface` or `ollama`. See
[ai-workflow/README.md](ai-workflow/README.md) for the variables each one needs.

### If something goes wrong

| You see | Fix |
| --- | --- |
| AI panel says the **index has not been built** (503) | Run `python ai-workflow/cli.py index`, then restart the API |
| AI panel says **OPENAI_API_KEY is not set** (503) | Put the key in `.env` (no quotes), restart the API |
| `429 ... no credits remaining` | Add credit under Billing on the OpenAI platform |
| `502 ... answer could not be used` | The model returned bad JSON; click again |
| Job list is empty / `postings_loaded: 0` at `/health` | Run `python -m backend.job_parser` |
| "Can't reach the server at http://127.0.0.1:8000" | Start the API (terminal 1) |
| Port already in use | Stop the other process, or pass `--port` to uvicorn and set `VITE_API_URL` |
| Collector fails on SSL certificates | `pip install -r requirements.txt` (it includes `certifi`) |

## Data pipeline

```bash
python fetch_postings.py                  # collect raw postings -> data/raw_postings.jsonl
python -m backend.job_parser              # parse -> data/parsed_postings.jsonl
python -m backend.gap_analysis --resume path/to/resume.pdf --rank     # rank all postings
python -m backend.gap_analysis --resume path/to/resume.pdf --posting-index 3
```

The command-line commands above are the rule-based baseline. The RAG equivalents are in
`ai-workflow/cli.py` (see step 4 above).

## Tests

```bash
pip install -r requirements-dev.txt
pytest                       # backend + RAG tests; no API key or network needed
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
ai-workflow/
  cli.py              command line for the RAG workflow
  internalign_rag/    FAISS knowledge base, LLM factory, RAG analysis, /rag routes
  README.md           RAG details and model options
frontend-web/src/
  App.jsx             login gate and session handling
  Dashboard.jsx       overview / job matches / my resume
  components/         JobCard, AnalysisPanel, ResumeView
  api.js              fetch wrapper
```
