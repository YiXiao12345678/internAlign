"""
InternAlign API.  Run from the project root with:

    uvicorn backend.api:app --reload

Routes
------
POST /signup, /login, GET /me           accounts (backend/auth_api.py)
GET  /health                            liveness check
GET  /postings                          list/search internship postings
GET  /postings/{id}                     one posting, fully parsed
POST /resume                            upload a resume (PDF/DOCX/TXT); replaces the active one
GET  /resume                            the active resume's metadata + detected skills
GET  /matches                           postings ranked by fit with the active resume
GET  /analysis/{posting_id}             gap analysis for one posting
"""
from __future__ import annotations

import re
import uuid

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import config
from .auth_api import get_current_user, router as auth_router
from .database import Base, engine, get_db
from .gap_analysis import analyze_posting, rank_postings
from .models import Resume, User
from .postings_store import get_posting, load_postings, posting_summary
from .resume_parser import ResumeParseError, extract_text_from_bytes, split_sections
from .skills import find_skills, label

Base.metadata.create_all(bind=engine)

app = FastAPI(title="InternAlign API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.get("/health")
def health():
    return {"status": "ok", "postings_loaded": len(load_postings())}


@app.get("/")
def root():
    return {"message": "InternAlign API is running"}


# --------------------------------------------------------------------------
# Postings
# --------------------------------------------------------------------------
@app.get("/postings")
def list_postings(
    q: str = Query("", description="Search company, title, location or skill"),
    limit: int = Query(50, ge=1, le=200),
    _user: User = Depends(get_current_user),
):
    needle = q.strip().lower()
    results = []
    for posting in load_postings():
        summary = posting_summary(posting)
        haystack = " ".join(
            [summary["company"], summary["title"], summary["location"], *summary["required_skills"], *summary["preferred_skills"]]
        ).lower()
        if needle in haystack:
            results.append(summary)
    return {"total": len(results), "postings": results[:limit]}


@app.get("/postings/{posting_id:path}")
def read_posting(posting_id: str, _user: User = Depends(get_current_user)):
    posting = get_posting(posting_id)
    if not posting:
        raise HTTPException(status_code=404, detail="Posting not found")
    return posting


# --------------------------------------------------------------------------
# Resume
# --------------------------------------------------------------------------
def _active_resume(db: Session, user: User) -> Resume | None:
    return (
        db.query(Resume)
        .filter(Resume.user_id == user.id)
        .order_by(Resume.created_at.desc(), Resume.id.desc())
        .first()
    )


def _resume_payload(resume: Resume) -> dict:
    sections = split_sections(resume.text)
    return {
        "id": resume.id,
        "filename": resume.filename,
        "uploaded_at": resume.created_at.isoformat() if resume.created_at else None,
        "characters": len(resume.text),
        "sections": sorted(name for name in sections if name != "header"),
        "skills": [{"name": s, "label": label(s)} for s in find_skills(resume.text)],
    }


def _require_resume(db: Session, user: User) -> Resume:
    resume = _active_resume(db, user)
    if not resume:
        raise HTTPException(status_code=404, detail="Upload a resume first.")
    return resume


@app.post("/resume", status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = await file.read(config.MAX_RESUME_BYTES + 1)
    if len(data) > config.MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail=f"File is too large. The limit is {config.MAX_RESUME_BYTES // (1024 * 1024)} MB.")

    filename = file.filename or "resume"
    try:
        text = extract_text_from_bytes(data, filename)
    except ResumeParseError as error:
        raise HTTPException(status_code=422, detail=str(error))

    # Keep the untouched original on disk. The stored name is generated, never the user's.
    suffix = re.sub(r"[^a-z0-9.]", "", filename.lower().rsplit(".", 1)[-1] if "." in filename else "")
    user_dir = config.UPLOAD_DIR / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    stored_path = user_dir / f"{uuid.uuid4().hex}.{suffix or 'bin'}"
    stored_path.write_bytes(data)

    resume = Resume(user_id=user.id, filename=filename[:255], stored_path=str(stored_path), text=text)
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return _resume_payload(resume)


@app.get("/resume")
def read_resume(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _resume_payload(_require_resume(db, user))


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------
@app.get("/matches")
def matches(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resume = _require_resume(db, user)
    ranked = rank_postings(load_postings(), resume.text)
    scored = [a["score"] for a in ranked if a["score"] is not None]
    return {
        "resume_id": resume.id,
        "total": len(ranked),
        "average_score": round(sum(scored) / len(scored)) if scored else None,
        "matches": [
            {
                "posting_id": a["posting_id"],
                "company": a["company"],
                "title": a["title"],
                "location": a["location"],
                "job_url": a["job_url"],
                "score": a["score"],
                "score_label": a["score_label"],
                "summary": a["summary"],
            }
            for a in ranked[:limit]
        ],
    }


@app.get("/analysis/{posting_id:path}")
def analysis(posting_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    resume = _require_resume(db, user)
    posting = get_posting(posting_id)
    if not posting:
        raise HTTPException(status_code=404, detail="Posting not found")
    return analyze_posting(posting, resume.text)
