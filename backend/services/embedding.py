import openai
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import AsyncOpenAI
from core.config import settings
from services.llm_provider_urls import build_llm_provider_http_client
from services.exceptions import EmbeddingGenerationError
from services.circuit_breaker import provider_circuit_breaker
from services.retry import retry_transient

STORAGE_EMBEDDING_DIMENSION = 1536


def chunk_text(
    text: str, chunk_size: int = 1000, chunk_overlap: int = 200
) -> list[str]:
    actual_overlap = min(chunk_overlap, chunk_size // 2)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=actual_overlap,
        length_function=len,
    )
    return splitter.split_text(text)


def fit_embedding_vector(
    embedding: list[float],
    target_dimension: int = STORAGE_EMBEDDING_DIMENSION,
) -> list[float]:
    if target_dimension <= 0:
        raise ValueError("target_dimension must be positive")

    if len(embedding) == target_dimension:
        return list(embedding)
    if len(embedding) < target_dimension:
        return [*embedding, *([0.0] * (target_dimension - len(embedding)))]
    return embedding[:target_dimension]


def _supports_native_dimensions(model: str) -> bool:
    """Return whether the selected OpenAI embedding family accepts dimensions."""
    return model.rsplit("/", 1)[-1].startswith("text-embedding-3-")


async def generate_embeddings(
    texts: list[str],
    openai_api_key: str,
    base_url: str | None = None,
    model: str | None = None,
) -> list[list[float]]:
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set")

    # Instantiate client locally to avoid global state race conditions across tenants
    configured_base_url = base_url if base_url is not None else settings.OPENAI_BASE_URL
    validated_base_url, http_client = await build_llm_provider_http_client(
        configured_base_url
    )
    client = AsyncOpenAI(
        api_key=openai_api_key,
        base_url=validated_base_url,
        http_client=http_client,
    )

    selected_model = model or settings.OPENAI_EMBEDDING_MODEL
    request = {"model": selected_model, "input": texts}
    if _supports_native_dimensions(selected_model):
        request["dimensions"] = STORAGE_EMBEDDING_DIMENSION

    try:
        response = await provider_circuit_breaker.call(
            validated_base_url or "openai-default",
            lambda: retry_transient(
                lambda: client.embeddings.create(**request),
                operation_name="embedding generation",
            ),
        )
        return [data.embedding for data in response.data]
    except openai.OpenAIError as e:
        raise EmbeddingGenerationError(f"Failed to generate embeddings: {str(e)}")
    finally:
        await client.close()
