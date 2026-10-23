"""RAG settings, read from environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# Where the collected postings (fetch_postings.py output) and the vector index live.
POSTINGS_PATH = Path(os.getenv("RAG_POSTINGS_PATH", PROJECT_ROOT / "data" / "raw_postings.jsonl"))
VECTOR_DB_PATH = Path(os.getenv("RAG_VECTOR_DB_PATH", PROJECT_ROOT / "data" / "faiss_index"))

# Embeddings run locally and are free
EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "100"))
TOP_K = int(os.getenv("RAG_TOP_K", "5"))

# Generation model
LLM_PROVIDER = os.getenv("RAG_LLM_PROVIDER", "openai").lower()
HF_MODEL = os.getenv("RAG_HF_MODEL", "Qwen/Qwen2.5-7B-Instruct")
OLLAMA_MODEL = os.getenv("RAG_OLLAMA_MODEL", "qwen2.5:7b-instruct")
OLLAMA_BASE_URL = os.getenv("RAG_OLLAMA_BASE_URL", "http://localhost:11434")
OPENAI_MODEL = os.getenv("RAG_OPENAI_MODEL", "gpt-4o-mini")
MAX_NEW_TOKENS = int(os.getenv("RAG_MAX_NEW_TOKENS", "1800"))
TEMPERATURE = float(os.getenv("RAG_TEMPERATURE", "0.01"))

MAX_RESUME_CHARS = int(os.getenv("RAG_MAX_RESUME_CHARS", "6000"))
