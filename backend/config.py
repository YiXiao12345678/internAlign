"""Settings read from environment variables (or a .env file in the project root)."""
import os
import warnings
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

_DEV_SECRET = "dev-only-secret-change-me"

SECRET_KEY = os.getenv("INTERNALIGN_SECRET_KEY", _DEV_SECRET)
if SECRET_KEY == _DEV_SECRET:
    warnings.warn(
        "INTERNALIGN_SECRET_KEY is not set; using an insecure development key. "
        "Set it in .env before deploying.",
        stacklevel=1,
    )

ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", "480"))

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

POSTINGS_PATH = Path(os.getenv("POSTINGS_PATH", PROJECT_ROOT / "data" / "parsed_postings.jsonl"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", PROJECT_ROOT / "uploads"))
MAX_RESUME_BYTES = int(os.getenv("MAX_RESUME_BYTES", str(5 * 1024 * 1024)))
