"""Chat-model factory. Heavy provider packages are imported only when that provider is used."""
from . import config

_llm = None
# Model name reported back by the provider on the latest call (e.g. gpt-4o-mini-2024-07-18).
last_model_used = None


class LLMNotConfigured(Exception):
    """Raised when the chosen provider is missing a key or a package."""


def _build_huggingface():
    import os

    token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
    if not token:
        raise LLMNotConfigured(
            "HUGGINGFACEHUB_API_TOKEN is not set. Create a free token at "
            "https://huggingface.co/settings/tokens and add it to .env."
        )
    from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint

    endpoint = HuggingFaceEndpoint(
        repo_id=config.HF_MODEL,
        task="text-generation",
        max_new_tokens=config.MAX_NEW_TOKENS,
        temperature=config.TEMPERATURE,
        huggingfacehub_api_token=token,
    )
    return ChatHuggingFace(llm=endpoint)


def _build_ollama():
    try:
        from langchain_ollama import ChatOllama
    except ImportError:
        raise LLMNotConfigured("Install langchain-ollama to use the ollama provider.")
    return ChatOllama(
        model=config.OLLAMA_MODEL,
        base_url=config.OLLAMA_BASE_URL,
        temperature=config.TEMPERATURE,
        num_predict=config.MAX_NEW_TOKENS,
    )


def _build_openai():
    import os

    if not os.getenv("OPENAI_API_KEY"):
        raise LLMNotConfigured(
            "OPENAI_API_KEY is not set. Create a key at https://platform.openai.com/api-keys "
            "and put it in .env as OPENAI_API_KEY=..."
        )
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise LLMNotConfigured("Install langchain-openai to use the openai provider.")
    return ChatOpenAI(
        model=config.OPENAI_MODEL,
        temperature=config.TEMPERATURE,
        max_tokens=config.MAX_NEW_TOKENS,
    )


def model_name() -> str:
    if config.LLM_PROVIDER == "huggingface":
        return config.HF_MODEL
    if config.LLM_PROVIDER == "ollama":
        return config.OLLAMA_MODEL
    if config.LLM_PROVIDER == "openai":
        return config.OPENAI_MODEL
    return "unknown"


def get_llm():
    """Return the configured chat model (created once)."""
    global _llm
    if _llm is None:
        if config.LLM_PROVIDER == "huggingface":
            _llm = _build_huggingface()
        elif config.LLM_PROVIDER == "ollama":
            _llm = _build_ollama()
        elif config.LLM_PROVIDER == "openai":
            _llm = _build_openai()
        else:
            raise LLMNotConfigured(
                f"Unknown RAG_LLM_PROVIDER '{config.LLM_PROVIDER}'. Use huggingface, ollama or openai."
            )
    return _llm


def ask(prompt: str, llm=None) -> str:
    """Send one prompt and return the reply as plain text."""
    global last_model_used
    model = llm if llm is not None else get_llm()
    reply = model.invoke(prompt)
    metadata = getattr(reply, "response_metadata", None)
    if isinstance(metadata, dict) and metadata.get("model_name"):
        last_model_used = metadata["model_name"]
    if hasattr(reply, "content"):
        return str(reply.content)
    return str(reply)
