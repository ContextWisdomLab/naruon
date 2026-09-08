import pytest
import openai
from unittest.mock import patch, AsyncMock
from services.embedding import (
    STORAGE_EMBEDDING_DIMENSION,
    chunk_text,
    fit_embedding_vector,
    generate_embeddings,
)
from services.exceptions import EmbeddingGenerationError


def test_chunk_text():
    text = "This is a long test string. " * 100
    chunks = chunk_text(text, chunk_size=50)
    assert len(chunks) > 1
    assert len(chunks[0]) <= 50


def test_fit_embedding_vector_pads_embeddinggemma_dimension_to_storage_vector():
    fitted = fit_embedding_vector([0.25] * 768)

    assert len(fitted) == STORAGE_EMBEDDING_DIMENSION
    assert fitted[:768] == [0.25] * 768
    assert fitted[768:] == [0.0] * (STORAGE_EMBEDDING_DIMENSION - 768)


def test_fit_embedding_vector_truncates_larger_provider_dimension():
    fitted = fit_embedding_vector([0.5] * 3072)

    assert len(fitted) == STORAGE_EMBEDDING_DIMENSION
    assert fitted == [0.5] * STORAGE_EMBEDDING_DIMENSION


@pytest.mark.asyncio
async def test_generate_embeddings_success():
    with patch(
        "services.embedding.AsyncOpenAI"
    ) as mock_async_openai:
        mock_client = mock_async_openai.return_value
        mock_client.close = AsyncMock()
        mock_client.embeddings.create = AsyncMock()
        mock_response = AsyncMock()
        mock_data_1 = AsyncMock()
        mock_data_1.embedding = [0.1, 0.2, 0.3]
        mock_data_2 = AsyncMock()
        mock_data_2.embedding = [0.4, 0.5, 0.6]
        mock_response.data = [mock_data_1, mock_data_2]
        mock_client.embeddings.create.return_value = mock_response

        with patch("services.embedding.settings") as mock_settings:
            mock_settings.OPENAI_EMBEDDING_MODEL = "test-model"
            mock_settings.OPENAI_BASE_URL = None
            
            embeddings = await generate_embeddings(["test1", "test2"], "test-key")
            assert len(embeddings) == 2
            assert embeddings[0] == [0.1, 0.2, 0.3]
            assert embeddings[1] == [0.4, 0.5, 0.6]
            mock_client.embeddings.create.assert_awaited_once_with(
                model="test-model", input=["test1", "test2"]
            )
            mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_embeddings_uses_selected_provider_model_and_base_url():
    with patch("services.embedding.AsyncOpenAI") as mock_async_openai, patch(
        "services.embedding.build_llm_provider_http_client",
        new_callable=AsyncMock,
    ) as mock_build_client:
        mock_http_client = AsyncMock()
        mock_build_client.return_value = ("http://ollama:11434/v1", mock_http_client)
        mock_client = mock_async_openai.return_value
        mock_client.close = AsyncMock()
        mock_client.embeddings.create = AsyncMock()
        mock_response = AsyncMock()
        mock_data = AsyncMock()
        mock_data.embedding = [0.1, 0.2, 0.3]
        mock_response.data = [mock_data]
        mock_client.embeddings.create.return_value = mock_response

        embeddings = await generate_embeddings(
            ["test"],
            "local-provider",
            base_url="http://ollama:11434/v1",
            model="embeddinggemma",
        )

    assert embeddings == [[0.1, 0.2, 0.3]]
    mock_build_client.assert_awaited_once_with("http://ollama:11434/v1")
    mock_client.embeddings.create.assert_awaited_once_with(
        model="embeddinggemma", input=["test"]
    )
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_embeddings_requests_storage_dimensions_for_openai_v3():
    with patch(
        "services.embedding.AsyncOpenAI"
    ) as mock_async_openai, patch(
        "services.embedding.build_llm_provider_http_client",
        new_callable=AsyncMock,
    ) as mock_build_client:
        mock_build_client.return_value = ("https://api.openai.com/v1", AsyncMock())
        mock_client = mock_async_openai.return_value
        mock_client.close = AsyncMock()
        mock_client.embeddings.create = AsyncMock()
        mock_response = AsyncMock()
        mock_data = AsyncMock()
        mock_data.embedding = [0.1, 0.2]
        mock_response.data = [mock_data]
        mock_client.embeddings.create.return_value = mock_response

        await generate_embeddings(
            ["test"],
            "provider-key",
            base_url="https://api.openai.com/v1",
            model="text-embedding-3-large",
        )

    mock_client.embeddings.create.assert_awaited_once_with(
        model="text-embedding-3-large",
        input=["test"],
        dimensions=STORAGE_EMBEDDING_DIMENSION,
    )


@pytest.mark.asyncio
async def test_generate_embeddings_api_error():
    with patch(
        "services.embedding.AsyncOpenAI"
    ) as mock_async_openai:
        mock_client = mock_async_openai.return_value
        mock_client.close = AsyncMock()
        mock_client.embeddings.create = AsyncMock(side_effect=openai.OpenAIError("API error"))

        with patch("services.embedding.settings") as mock_settings:
            mock_settings.OPENAI_EMBEDDING_MODEL = "test-model"
            mock_settings.OPENAI_BASE_URL = None
            
            with pytest.raises(EmbeddingGenerationError, match="Failed to generate embeddings: API error"):

                await generate_embeddings(["test"], "test-key")
            mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_embeddings_missing_key():
    with pytest.raises(ValueError, match="OPENAI_API_KEY is not set"):
        await generate_embeddings(["test"], "")
