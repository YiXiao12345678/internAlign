"""
End-to-end API tests. They need the web dependencies (requirements-dev.txt).
Environment is pointed at throwaway paths *before* the app is imported.
"""
import json
import os
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

_tmp = Path(tempfile.mkdtemp())
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["UPLOAD_DIR"] = str(_tmp / "uploads")
os.environ["POSTINGS_PATH"] = str(_tmp / "postings.jsonl")
os.environ["INTERNALIGN_SECRET_KEY"] = "test-secret"

(_tmp / "postings.jsonl").write_text(
    json.dumps({"id": "t:1", "company": "Acme", "title": "SWE Intern", "location": "Remote",
                "required_skills": ["python", "rust"], "preferred_skills": []}) + "\n",
    encoding="utf-8",
)

from fastapi.testclient import TestClient  # noqa: E402

from backend.api import app  # noqa: E402

client = TestClient(app)
RESUME = b"Sam Student\nSKILLS\nPython, Java\nEXPERIENCE\n- Built a Python tool for log validation at a lab\n"


def _login(email="sam@example.com"):
    client.post("/signup", json={"name": "Sam", "email": email, "password": "password123"})
    token = client.post("/login", json={"email": email, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_requires_login():
    assert client.get("/postings").status_code == 401
    assert client.get("/matches").status_code == 401


def test_signup_validation_and_wrong_password():
    assert client.post("/signup", json={"name": "A", "email": "nope", "password": "password123"}).status_code == 422
    assert client.post("/signup", json={"name": "A", "email": "a@b.co", "password": "short"}).status_code == 400
    _login("dup@example.com")
    assert client.post("/signup", json={"name": "A", "email": "dup@example.com", "password": "password123"}).status_code == 400
    assert client.post("/login", json={"email": "dup@example.com", "password": "wrongpass1"}).status_code == 401


def test_full_flow():
    headers = _login()
    assert client.get("/matches", headers=headers).status_code == 404  # no resume yet

    assert client.post("/resume", headers=headers, files={"file": ("r.exe", b"x", "application/octet-stream")}).status_code == 422
    upload = client.post("/resume", headers=headers, files={"file": ("resume.txt", RESUME, "text/plain")})
    assert upload.status_code == 201
    assert {"python", "java"} <= {s["name"] for s in upload.json()["skills"]}

    postings = client.get("/postings", headers=headers).json()
    assert postings["total"] == 1

    matches = client.get("/matches", headers=headers).json()
    assert matches["matches"][0]["score"] == 50

    detail = client.get("/analysis/t:1", headers=headers).json()
    statuses = {r["requirement"]: r["status"] for r in detail["requirements"]}
    assert statuses == {"python": "Supported", "rust": "Not found"}
    assert client.get("/analysis/nope", headers=headers).status_code == 404
