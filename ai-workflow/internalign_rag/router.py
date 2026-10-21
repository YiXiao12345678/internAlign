"""
FastAPI routes for the RAG workflow.

The router is built from three pieces supplied by the main API (auth, database
session and a way to read the signed-in user's resume text), so this package
never imports from backend/ and can be tested on its own.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from . import analysis, config, knowledge_base, llm


def build_router(auth_dependency, db_dependency, load_resume_text) -> APIRouter:
    """`load_resume_text(user, db)` must return the active resume's text or raise HTTPException."""
    router = APIRouter(prefix="/rag", tags=["rag"])

    @router.get("/status")
    def rag_status(_user=Depends(auth_dependency)):
        built = knowledge_base.index_exists()
        return {
            "index_built": built,
            "chunks": knowledge_base.chunk_count() if built else 0,
            "provider": config.LLM_PROVIDER,
            "model": llm.model_name(),
            "embedding_model": config.EMBEDDING_MODEL,
        }

    @router.get("/analysis/{posting_id:path}")
    def rag_analysis(
        posting_id: str,
        user=Depends(auth_dependency),
        db=Depends(db_dependency),
    ):
        resume_text = load_resume_text(user, db)
        try:
            return analysis.analyze(resume_text, posting_id)
        except knowledge_base.IndexNotBuilt as error:
            raise HTTPException(status_code=503, detail=str(error))
        except KeyError:
            raise HTTPException(status_code=404, detail="Posting not found in the RAG index.")
        except llm.LLMNotConfigured as error:
            raise HTTPException(status_code=503, detail=str(error))
        except analysis.AnalysisError as error:
            raise HTTPException(status_code=502, detail=f"The model's answer could not be used. {error}")
        except Exception as error:
            raise HTTPException(status_code=502, detail=f"The language model request failed: {error}")

    @router.get("/matches")
    def rag_matches(
        limit: int = Query(10, ge=1, le=50),
        user=Depends(auth_dependency),
        db=Depends(db_dependency),
    ):
        resume_text = load_resume_text(user, db)
        queries = analysis.resume_queries(resume_text)
        try:
            ranked = knowledge_base.match_postings(queries, top_postings=limit)
        except knowledge_base.IndexNotBuilt as error:
            raise HTTPException(status_code=503, detail=str(error))
        return {"total": len(ranked), "matches": ranked}

    return router
