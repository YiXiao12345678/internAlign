---
name: rag-system-reference
description: Use when building, changing or running the InternAlign RAG workflow in ai-workflow/ (retrieval, embeddings, vector store, LLM choice), or when asked how the author's reference RAG app is built.
---

# RAG reference

The author's reference app: https://github.com/yuji-nishi-12/rag-system-app (one commit, March 2026,
a local RAG over a single PDF).

## How the reference is built
- `rag.py`: `PyPDFLoader` -> `RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)` ->
  `HuggingFaceEmbeddings("sentence-transformers/all-MiniLM-L6-v2")` -> `QdrantVectorStore` in local mode
  (`path="./qdrant_db"`). Retriever: similarity search, `k=5`. Generation: `HuggingFaceEndpoint`
  (`Qwen/Qwen2.5-3B-Instruct`, `temperature=0.01`, token from `HUGGINGFACEHUB_API_TOKEN`).
  The prompt is "context + question" with no rules.
- `endpoints.py` / `main.py`: FastAPI `GET /query/?q=...`.
- Requirements: fastapi, uvicorn, pypdf, sentence-transformers, langchain, langchain-huggingface,
  langchain-community, langchain-text-splitters, langchain-qdrant, qdrant-client, streamlit.

## How InternAlign follows and differs from it
- Same idea: LangChain + MiniLM embeddings + a local vector store. The reference uses Qdrant; InternAlign
  uses FAISS because the project doc (cs152_project.md) specifies ChromaDB or FAISS.
- Differences: many postings instead of one PDF (chunks carry `posting_id` metadata so hits map back
  to a posting); GPT-4o-mini by default; provider switch (openai | huggingface | ollama) through
  `RAG_LLM_PROVIDER`; structured JSON output with every resume quote verified against the resume text.
- Code lives in `ai-workflow/internalign_rag/`; `backend/api.py` mounts its router under `/rag`.
  Details and run steps: `ai-workflow/README.md`.

## Rules for changes here
- Never let the model's claim count as evidence unless the quoted line is in the resume.
- Keep the analysis JSON shape identical to `backend/gap_analysis.analyze_posting`.
- No comprehensions, lambdas or generator expressions in new code (the author's preference).
- The FAISS index is saved to data/faiss_index and loaded once per process; re-run `cli.py index`
  after the postings change and restart the API.
