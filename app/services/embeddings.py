import numpy as np
from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_openai import OpenAIEmbeddings

from app.core.config import settings


def _normalize(vectors: list[list[float]]) -> list[list[float]]:
    arr = np.array(vectors, dtype=np.float64)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (arr / norms).tolist()


class NormalizedEmbeddings(Embeddings):
    """Envuelve el Embeddings de LangChain del proveedor activo y normaliza
    L2 cada vector antes de devolverlo. gemini-embedding-001 no normaliza
    los vectores truncados vía output_dimensionality (a diferencia de
    text-embedding-3-small); normalizar siempre acá evita que la similitud
    coseno en pgvector dependa de una garantía específica del proveedor."""

    def __init__(self, inner: Embeddings):
        self._inner = inner

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return _normalize(self._inner.embed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return _normalize([self._inner.embed_query(text)])[0]


def get_embeddings() -> NormalizedEmbeddings:
    if settings.llm_provider == "gemini":
        inner: Embeddings = GoogleGenerativeAIEmbeddings(
            model=settings.gemini_embedding_model,
            google_api_key=settings.gemini_api_key,
            output_dimensionality=settings.embedding_dims,
        )
    else:
        inner = OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
            dimensions=settings.embedding_dims,
        )
    return NormalizedEmbeddings(inner)
