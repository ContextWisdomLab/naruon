"""Regression coverage for exception logging disclosure boundaries."""

import datetime
import io
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import import_fixtures
from scripts import import_fixtures as zip_import_fixtures

_SECRET_EXCEPTION_TEXT = "provider token=super-secret-value"
_SECRET_FIXTURE_PATH = "/private/customer/secret-message.eml"


def _parsed_email(*, attachments: list[dict[str, str]] | None = None) -> dict:
    return {
        "message_id": "<fixture@example.com>",
        "sender": "sender@example.com",
        "recipients": "user@example.com",
        "subject": "Fixture",
        "date": datetime.datetime.now(datetime.timezone.utc),
        "body": "Body",
        "attachments": attachments or [],
    }


class _NoExistingResult:
    def scalar_one_or_none(self):
        return None


class _FixtureSession:
    def __init__(self, *, commit_error: Exception | None = None):
        self.added = None
        self.committed = False
        self.rolled_back = False
        self.commit_error = commit_error

    async def execute(self, _query):
        return _NoExistingResult()

    def add(self, obj):
        self.added = obj

    async def commit(self):
        if self.commit_error is not None:
            raise self.commit_error
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _render_exc_info_true_log() -> str:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("naruon.test.exception_redaction")
    previous_handlers = list(logger.handlers)
    previous_propagate = logger.propagate
    previous_level = logger.level
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.ERROR)
    try:
        try:
            raise RuntimeError(_SECRET_EXCEPTION_TEXT)
        except RuntimeError:
            logger.error("Provider operation failed", exc_info=True)
        return stream.getvalue()
    finally:
        logger.handlers = previous_handlers
        logger.propagate = previous_propagate
        logger.setLevel(previous_level)


def test_process_logging_policy_redacts_exc_info_true_exception_values() -> None:
    rendered = _render_exc_info_true_log()

    assert _SECRET_EXCEPTION_TEXT not in rendered
    assert "token=" not in rendered
    assert "Exception details redacted" in rendered
    assert "_render_exc_info_true_log" in rendered


@pytest.mark.asyncio
async def test_root_fixture_parse_failure_logs_bounded_message(caplog, tmp_path) -> None:
    session = _FixtureSession()
    eml_file = tmp_path / "secret-message.eml"

    with caplog.at_level(logging.ERROR, logger=import_fixtures.logger.name), patch.object(
        import_fixtures,
        "parse_eml",
        side_effect=RuntimeError(f"{_SECRET_EXCEPTION_TEXT} {_SECRET_FIXTURE_PATH}"),
    ):
        imported = await import_fixtures.import_eml_file(session, eml_file)

    assert imported is False
    assert "Fixture email parsing failed" in caplog.text
    assert _SECRET_EXCEPTION_TEXT not in caplog.text
    assert _SECRET_FIXTURE_PATH not in caplog.text
    assert str(eml_file) not in caplog.text


@pytest.mark.asyncio
async def test_root_fixture_body_embedding_failure_logs_bounded_message(
    caplog, tmp_path
) -> None:
    session = _FixtureSession()
    eml_file = tmp_path / "secret-body.eml"

    with caplog.at_level(logging.ERROR, logger=import_fixtures.logger.name), patch.object(
        import_fixtures, "parse_eml", return_value=_parsed_email()
    ), patch.object(
        import_fixtures,
        "generate_fixture_embedding",
        new=AsyncMock(side_effect=RuntimeError(_SECRET_EXCEPTION_TEXT)),
    ):
        imported = await import_fixtures.import_eml_file(session, eml_file)

    assert imported is False
    assert "Fixture email body embedding failed" in caplog.text
    assert _SECRET_EXCEPTION_TEXT not in caplog.text
    assert str(eml_file) not in caplog.text


@pytest.mark.asyncio
async def test_root_fixture_attachment_embedding_failure_skips_attachment_safely(
    caplog, tmp_path
) -> None:
    session = _FixtureSession()
    eml_file = tmp_path / "secret-attachment.eml"
    parsed = _parsed_email(
        attachments=[{"filename": "customer-secret.txt", "content": "attachment body"}]
    )
    embedding = [0.0] * import_fixtures.EMBEDDING_DIMENSION

    with caplog.at_level(logging.ERROR, logger=import_fixtures.logger.name), patch.object(
        import_fixtures, "parse_eml", return_value=parsed
    ), patch.object(
        import_fixtures,
        "generate_fixture_embedding",
        new=AsyncMock(side_effect=[embedding, RuntimeError(_SECRET_EXCEPTION_TEXT)]),
    ), patch.object(
        import_fixtures,
        "assign_thread_id",
        new=AsyncMock(return_value="fixture-thread"),
    ):
        imported = await import_fixtures.import_eml_file(session, eml_file)

    assert imported is True
    assert session.committed is True
    assert session.added is not None
    assert list(session.added.attachments) == []
    assert "Fixture attachment embedding failed" in caplog.text
    assert _SECRET_EXCEPTION_TEXT not in caplog.text
    assert "customer-secret.txt" not in caplog.text
    assert str(eml_file) not in caplog.text


@pytest.mark.asyncio
async def test_root_fixture_commit_failure_rolls_back_without_sensitive_log(
    caplog, tmp_path
) -> None:
    session = _FixtureSession(commit_error=RuntimeError(_SECRET_EXCEPTION_TEXT))
    eml_file = tmp_path / "secret-commit.eml"
    embedding = [0.0] * import_fixtures.EMBEDDING_DIMENSION

    with caplog.at_level(logging.ERROR, logger=import_fixtures.logger.name), patch.object(
        import_fixtures, "parse_eml", return_value=_parsed_email()
    ), patch.object(
        import_fixtures,
        "generate_fixture_embedding",
        new=AsyncMock(return_value=embedding),
    ), patch.object(
        import_fixtures,
        "assign_thread_id",
        new=AsyncMock(return_value="fixture-thread"),
    ):
        imported = await import_fixtures.import_eml_file(session, eml_file)

    assert imported is False
    assert session.rolled_back is True
    assert "Fixture email commit failed" in caplog.text
    assert _SECRET_EXCEPTION_TEXT not in caplog.text
    assert str(eml_file) not in caplog.text


@pytest.mark.asyncio
async def test_zip_fixture_parse_failure_logs_bounded_message(caplog) -> None:
    file_path = Path(_SECRET_FIXTURE_PATH)
    session = AsyncMock()

    with caplog.at_level(
        logging.ERROR, logger=zip_import_fixtures.logger.name
    ), patch.object(
        zip_import_fixtures,
        "extract_backup_async",
        new=AsyncMock(return_value=[file_path]),
    ), patch.object(
        zip_import_fixtures,
        "parse_eml",
        side_effect=RuntimeError(_SECRET_EXCEPTION_TEXT),
    ):
        await zip_import_fixtures.process_zip_file("fixture.zip", session)

    assert "Fixture archive email parsing failed" in caplog.text
    assert _SECRET_EXCEPTION_TEXT not in caplog.text
    assert _SECRET_FIXTURE_PATH not in caplog.text
