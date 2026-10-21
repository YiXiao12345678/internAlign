"""
Command-line access to the RAG workflow. Run from the project root:

    python ai-workflow/cli.py index
    python ai-workflow/cli.py status
    python ai-workflow/cli.py search "backend python internship" [--posting-id ID]
    python ai-workflow/cli.py match --resume path/to/resume.pdf
    python ai-workflow/cli.py analyze --resume path/to/resume.pdf --posting-id ID
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from internalign_rag import analysis, config, knowledge_base, llm  # noqa: E402


def read_resume(path: str) -> str:
    from backend.resume_parser import extract_resume_text

    return extract_resume_text(path)


def command_index(args):
    count = knowledge_base.build_index()
    print(f"Indexed {count} chunks into {config.VECTOR_DB_PATH}")


def command_status(args):
    built = knowledge_base.index_exists()
    print(f"Index built:     {built}")
    if built:
        print(f"Chunks:          {knowledge_base.chunk_count()}")
    print(f"Embedding model: {config.EMBEDDING_MODEL}")
    print(f"LLM:             {config.LLM_PROVIDER} / {llm.model_name()}")


def command_search(args):
    hits = knowledge_base.search(args.query, k=args.k, posting_id=args.posting_id)
    for hit in hits:
        preview = hit["text"].replace("\n", " ")[:160]
        print(f"{hit['score']:.3f}  {hit['company']} - {hit['title']}  [{hit['posting_id']}]")
        print(f"       {preview}")


def command_match(args):
    queries = analysis.resume_queries(read_resume(args.resume))
    for rank, item in enumerate(knowledge_base.match_postings(queries, top_postings=args.top), 1):
        print(f"{rank:>2}. {item['score']:.3f}  {item['company']} - {item['title']}  [{item['posting_id']}]")


def command_analyze(args):
    result = analysis.analyze(read_resume(args.resume), args.posting_id)
    print(f"{result['company']} - {result['title']}  ({result['model']})")
    print(f"Score: {result['score']} ({result['score_label']})  {result['summary']}")
    print(f"Unverified quotes removed: {result['unverified_quotes_removed']}")
    for req in result["requirements"]:
        print(f"  [{req['status']:<19}] {req['importance']:<9} {req['requirement']}")
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved to {args.output}")


def main():
    parser = argparse.ArgumentParser(description="InternAlign RAG workflow")
    commands = parser.add_subparsers(dest="command", required=True)

    index = commands.add_parser("index", help="Embed the collected postings and save the FAISS index (replaces any existing one)")
    index.set_defaults(handler=command_index)

    status = commands.add_parser("status", help="Show index and model settings")
    status.set_defaults(handler=command_status)

    search = commands.add_parser("search", help="Search the index")
    search.add_argument("query")
    search.add_argument("-k", type=int, default=config.TOP_K)
    search.add_argument("--posting-id")
    search.set_defaults(handler=command_search)

    match = commands.add_parser("match", help="Find postings that fit a resume")
    match.add_argument("--resume", required=True)
    match.add_argument("--top", type=int, default=10)
    match.set_defaults(handler=command_match)

    analyze = commands.add_parser("analyze", help="RAG gap analysis of a resume against one posting")
    analyze.add_argument("--resume", required=True)
    analyze.add_argument("--posting-id", required=True)
    analyze.add_argument("--output")
    analyze.set_defaults(handler=command_analyze)

    args = parser.parse_args()
    try:
        args.handler(args)
    except (knowledge_base.IndexNotBuilt, llm.LLMNotConfigured, FileNotFoundError, KeyError) as error:
        print(f"Error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
