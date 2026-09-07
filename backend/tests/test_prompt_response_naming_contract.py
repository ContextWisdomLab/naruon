"""Naming and public-identifier contract for prompt responses."""

from __future__ import annotations

import datetime
from types import SimpleNamespace

from api.prompts import PromptResponse


def _prompt_record() -> SimpleNamespace:
    """Return an ORM-shaped prompt record that still contains its private row id."""
    now = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)
    return SimpleNamespace(
        id=17,
        prompt_uid="prompt-example",
        title="Example",
        description=None,
        content="Summarize {{email}}",
        is_shared=False,
        created_by="user-example",
        created_at=now,
        updated_at=now,
    )


def test_prompt_response_uses_only_opaque_public_identifier() -> None:
    """Sequential database identity must not enter the owned API response model."""
    assert "prompt_uid" in PromptResponse.model_fields
    assert "id" not in PromptResponse.model_fields
    assert "prompt_record_id" not in PromptResponse.model_fields

    prompt_response = PromptResponse.model_validate(_prompt_record())
    serialized_response = prompt_response.model_dump()

    assert serialized_response["prompt_uid"] == "prompt-example"
    assert "id" not in serialized_response
    assert "prompt_record_id" not in serialized_response


def test_prompt_response_json_schema_does_not_advertise_sequential_database_id() -> None:
    """FastAPI's response schema must advertise the opaque UID as the sole identifier."""
    response_properties = PromptResponse.model_json_schema()["properties"]

    assert "prompt_uid" in response_properties
    assert "id" not in response_properties
    assert "prompt_record_id" not in response_properties
