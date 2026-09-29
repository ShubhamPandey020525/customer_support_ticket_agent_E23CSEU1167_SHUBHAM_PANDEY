from langchain_openai import ChatOpenAI

from src.config import Settings


def build_chat_model(settings: Settings) -> ChatOpenAI:
    """Create the configured LangChain chat-model adapter.

    Speed optimisations applied:
    - temperature=0.1  -> more deterministic, faster token selection
    - max_tokens=512   -> hard cap prevents the model generating walls of text
    - max_retries=1    -> fail fast
    - timeout=60       -> generous wall-clock limit for slow local inference
    """
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=0.1,
        max_tokens=512,
        max_retries=1,
        timeout=60,
    )
