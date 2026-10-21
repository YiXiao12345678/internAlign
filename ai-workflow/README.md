# ai-workflow: RAG gap analysis

Retrieval-augmented analysis of a resume against internship postings. It sits
next to the rule-based code in `backend/` and returns the same JSON shape, so the
React dashboard can show both and the two methods can be compared.

```
data/raw_postings.jsonl  ->  chunk + embed  ->  FAISS index (data/faiss_index)
                                                    |
resume + posting id  ->  retrieve posting chunks  ->  language model  ->  verify quotes  ->  analysis JSON
```

Nothing the model says counts as evidence unless the quoted line really appears in
the resume. Unverifiable "Supported" claims are downgraded to "Not found".

## Setup

From the project root, with the main requirements already installed:

```bash
pip install -r ai-workflow/requirements.txt
```

Collect postings if you have not (`python fetch_postings.py`), then build the index.
The first run downloads the embedding model (about 90 MB):

```bash
python ai-workflow/cli.py index            # always rebuilds from scratch
python ai-workflow/cli.py status
python ai-workflow/cli.py search "backend python internship"
```

Rebuild the index whenever `data/raw_postings.jsonl` changes, then restart the API
so it loads the new index.

## Choosing the language model

Set these in `.env` (see `.env.example`). No code changes are needed to switch.

| Provider | Variables | Notes |
|---|---|---|
| `openai` (default) | `OPENAI_API_KEY`, `RAG_OPENAI_MODEL` | `gpt-4o-mini` by default. Create a key at platform.openai.com/api-keys (needs prepaid billing credit) |
| `huggingface` | `HUGGINGFACEHUB_API_TOKEN`, `RAG_HF_MODEL` | Open-source model (default `Qwen/Qwen2.5-7B-Instruct`), hosted by Hugging Face. Free token: huggingface.co/settings/tokens |
| `ollama` | `RAG_OLLAMA_MODEL`, `RAG_OLLAMA_BASE_URL` | Open-source model on your own machine. Install Ollama, then `ollama pull qwen2.5:7b-instruct`. Needs `pip install langchain-ollama` |

Small models sometimes return malformed JSON. The API then answers 502 with a
message instead of a made-up analysis; try again or use a larger model.

## Run it with the web app

```bash
uvicorn backend.api:app --reload                 # terminal 1, http://127.0.0.1:8000
cd frontend-web && npm run dev                   # terminal 2, http://localhost:5173
```

Sign in, upload a resume, open a job, and choose **AI (RAG)** above the analysis.
`backend/api.py` mounts the routes below when this folder is present:

| Route | Purpose |
|---|---|
| `GET /rag/status` | Is the index built, which model and embeddings are configured |
| `GET /rag/matches?limit=10` | Postings closest to the active resume |
| `GET /rag/analysis/{posting_id}` | RAG gap analysis, same shape as `/analysis/{posting_id}` |

Command-line versions, no web app needed:

```bash
python ai-workflow/cli.py match   --resume path/to/resume.pdf
python ai-workflow/cli.py analyze --resume path/to/resume.pdf --posting-id "greenhouse:databricks:6865687002"
```

## Tests

```bash
pytest ai-workflow/tests
```

They use a fake embedding model and a fake language model, so they run offline.
They check indexing and search, the quote-verification rule, scoring and the routes.

## Layout

```
ai-workflow/
  cli.py                   command-line entry point
  internalign_rag/
    config.py              settings from environment variables
    llm.py                 model factory (huggingface | ollama | openai)
    knowledge_base.py      chunk, embed, store, search, rank postings
    analysis.py            prompt, JSON parsing, quote verification, scoring
    router.py              FastAPI routes, mounted by backend/api.py
  tests/test_rag.py
```

## Known limits

- Postings are indexed as raw text. Once the extraction model exists, embed its
  structured fields instead (the proposal's design) and compare retrieval quality.
- `evidence_type` ("listed" vs "demonstrated") is a heuristic based on line length.
- Component 2's remaining steps (answering clarifying questions, revising the
  resume, export) are not built here yet.
