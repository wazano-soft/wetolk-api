from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.core.config import settings


def get_chat_model(temperature: float = 0.0) -> BaseChatModel:
    """Devuelve el chat model del proveedor activo (LLM_PROVIDER). Ambos
    implementan la misma interfaz de LangChain (BaseChatModel), así que el
    resto del código nunca importa el SDK de OpenAI o Gemini directamente."""
    if settings.llm_provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=settings.gemini_llm_model,
            google_api_key=settings.gemini_api_key,
            temperature=temperature,
        )
    return ChatOpenAI(
        model=settings.openai_llm_model,
        api_key=settings.openai_api_key,
        temperature=temperature,
    )
