"""
Knowledge base: chunk the collected postings, embed them, store them in a local
FAISS index, and search it.

For now the postings are indexed as raw text (the structured extractor from
Component 1 does not exist yet). Every chunk carries the posting id in its
metadata, so a hit always maps back to the posting it came from.

Scores are cosine similarities (higher is better). The index is saved to disk
with save_local and loaded once per process.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config

_embeddings = None
_store = None
_store_path = None
_posting_info: dict = {}
_posting_chunks: dict = {}


class IndexNotBuilt(Exception):
    """Raised when a search is attempted before the index exists."""


def read_postings(path: Path | str) -> list[dict]:
    """Read one JSON posting per line, skipping blank lines."""
    postings = []
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                postings.append(json.loads(line))
    return postings


def set_embeddings(embeddings) -> None:
    """Swap the embedding model (used by tests)."""
    global _embeddings
    _embeddings = embeddings


def get_embeddings():
    global _embeddings
    if _embeddings is None:
        from langchain_huggingface import HuggingFaceEmbeddings

        # Unit-length vectors make the inner product a cosine similarity for any model.
        _embeddings = HuggingFaceEmbeddings(
            model_name=config.EMBEDDING_MODEL,
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embeddings


def reset() -> None:
    """Forget the loaded index so the next call reads it from disk again."""
    global _store, _store_path, _posting_info, _posting_chunks
    _store = None
    _store_path = None
    _posting_info = {}
    _posting_chunks = {}


def index_exists() -> bool:
    return (Path(config.VECTOR_DB_PATH) / "index.faiss").exists()


def _remember_postings(store) -> None:
    """Map each posting id to its metadata, so lookups do not need a search."""
    global _posting_info, _posting_chunks
    _posting_info = {}
    _posting_chunks = {}
    for docstore_id in store.index_to_docstore_id.values():
        document = store.docstore.search(docstore_id)
        posting_id = document.metadata.get("posting_id", "")
        if not posting_id:
            continue
        if posting_id not in _posting_info:
            _posting_info[posting_id] = document.metadata
        chunks = _posting_chunks.setdefault(posting_id, [])
        chunks.append((document.metadata.get("chunk_index", 0), document.page_content))


def _faiss_options() -> dict:
    from langchain_community.vectorstores.utils import DistanceStrategy

    # Inner product on the unit-length vectors from get_embeddings() = cosine similarity.
    return {"distance_strategy": DistanceStrategy.MAX_INNER_PRODUCT}


def chunk_count() -> int:
    if not index_exists():
        return 0
    return _load_store().index.ntotal


def build_documents(postings: list[dict]) -> list:
    """Split every posting into overlapping chunks, each prefixed with company and title."""
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP
    )
    documents = []
    for posting in postings:
        text = posting.get("text", "") or ""
        if not text.strip():
            continue
        header = f"{posting.get('company', '')} - {posting.get('title', '')}"
        pieces = splitter.split_text(text)
        for index, piece in enumerate(pieces):
            documents.append(
                Document(
                    page_content=f"{header}\n{piece}",
                    metadata={
                        "posting_id": posting.get("id", ""),
                        "company": posting.get("company", ""),
                        "title": posting.get("title", ""),
                        "location": posting.get("location", ""),
                        "url": posting.get("url", ""),
                        "chunk_index": index,
                    },
                )
            )
    return documents


def build_index(postings_path: Path | str | None = None) -> int:
    """Embed all postings and save the FAISS index. Returns the number of chunks stored."""
    global _store, _store_path
    from langchain_community.vectorstores import FAISS

    source = Path(postings_path if postings_path is not None else config.POSTINGS_PATH)
    if not source.exists():
        raise FileNotFoundError(
            f"{source} not found. Run `python fetch_postings.py` first to collect postings."
        )
    documents = build_documents(read_postings(source))
    if not documents:
        raise ValueError(f"No postings with text were found in {source}.")

    store = FAISS.from_documents(documents, get_embeddings(), **_faiss_options())
    Path(config.VECTOR_DB_PATH).mkdir(parents=True, exist_ok=True)
    store.save_local(str(config.VECTOR_DB_PATH))

    _store = store
    _store_path = str(config.VECTOR_DB_PATH)
    _remember_postings(store)
    return len(documents)


def _load_store():
    """Load the saved index once per process (and again if the path changes)."""
    global _store, _store_path
    from langchain_community.vectorstores import FAISS

    if not index_exists():
        raise IndexNotBuilt(
            "The posting index has not been built yet. Run: python ai-workflow/cli.py index"
        )
    target = str(config.VECTOR_DB_PATH)
    if _store is None or _store_path != target:
        # The index files are written by build_index on this machine, so loading
        # the pickled document store is safe.
        _store = FAISS.load_local(
            target,
            get_embeddings(),
            allow_dangerous_deserialization=True,
            **_faiss_options(),
        )
        _store_path = target
        _remember_postings(_store)
    return _store


def search(query: str, k: int | None = None, posting_id: str | None = None) -> list[dict]:
    """Top-k chunks for `query`, optionally limited to one posting."""
    store = _load_store()
    wanted = k or config.TOP_K
    if posting_id:
        # FAISS filters after the search, so look through every chunk to find this posting's.
        hits = store.similarity_search_with_score(
            query, k=wanted, filter={"posting_id": posting_id}, fetch_k=store.index.ntotal
        )
    else:
        hits = store.similarity_search_with_score(query, k=wanted)
    results = []
    for document, score in hits:
        results.append(
            {
                "text": document.page_content,
                "score": float(score),
                "posting_id": document.metadata.get("posting_id", ""),
                "company": document.metadata.get("company", ""),
                "title": document.metadata.get("title", ""),
                "location": document.metadata.get("location", ""),
                "url": document.metadata.get("url", ""),
                "chunk_index": document.metadata.get("chunk_index", 0),
            }
        )
    return results


def posting_metadata(posting_id: str) -> dict | None:
    """Company, title, location and URL of a posting, or None if it is not indexed."""
    _load_store()
    return _posting_info.get(posting_id)


def posting_text(posting_id: str) -> str:
    """All indexed text of a posting, in reading order (chunk overlaps may repeat a few words)."""
    _load_store()
    chunks = sorted(_posting_chunks.get(posting_id, []), key=_by_chunk_index)
    texts = []
    for _, text in chunks:
        texts.append(text)
    return "\n".join(texts)


def _by_chunk_index(item: tuple) -> int:
    return item[0]


def match_postings(queries: list[str], top_postings: int = 10, chunks_per_query: int = 20) -> list[dict]:
    """
    Rank postings against a resume. Each query (a resume section) finds its
    closest chunks; a posting's score for a query is its best chunk, and the
    final score is the average over all queries.
    """
    if not queries:
        return []
    best_per_query: dict[str, list[float]] = {}
    info: dict[str, dict] = {}
    for query_number, query in enumerate(queries):
        for hit in search(query, k=chunks_per_query):
            posting_id = hit["posting_id"]
            scores = best_per_query.setdefault(posting_id, [0.0] * len(queries))
            if hit["score"] > scores[query_number]:
                scores[query_number] = hit["score"]
            info[posting_id] = hit

    ranked = []
    for posting_id, scores in best_per_query.items():
        hit = info[posting_id]
        ranked.append(
            {
                "posting_id": posting_id,
                "company": hit["company"],
                "title": hit["title"],
                "location": hit["location"],
                "url": hit["url"],
                "score": sum(scores) / len(queries),
            }
        )
    ranked.sort(key=_by_score, reverse=True)
    return ranked[:top_postings]


def _by_score(item: dict) -> float:
    return item["score"]
