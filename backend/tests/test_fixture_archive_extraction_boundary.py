"""Regression coverage for fixture archive extraction failure boundaries."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts import import_fixtures as zip_import_fixtures
from services.exceptions import ArchiveError

_SECRET_EXCEPTION_TEXT = "provider token=super-secret-value"
_SECRET_FIXTURE_PATH = "/private/customer/customer-secret.zip"


@pytest.mark.asyncio
async def test_expected_archive_error_is_bounded_and_consumed(caplog, tmp_path) -> None:
    session = MagicMock()
    zip_path = tmp_path / "customer-secret.zip"

    with caplog.at_level(
        logging.INFO, logger=zip_import_fixtures.logger.name
    ), patch.object(
        zip_import_fixtures,
        "extract_backup_async",
        new=AsyncMock(
            side_effect=ArchiveError(
                f"{_SECRET_EXCEPTION_TEXT} {_SECRET_FIXTURE_PATH}"
            )
        ),
    ):
        await zip_import_fixtures.process_zip_file(zip_path, session)

    assert "Fixture archive extraction failed" in caplog.text
    assert "Extracting fixture archive" in caplog.text
    assert "Finished processing fixture archive" not in caplog.text
    assert _SECRET_EXCEPTION_TEXT not in caplog.text
    assert _SECRET_FIXTURE_PATH not in caplog.text
    assert str(zip_path) not in caplog.text


@pytest.mark.asyncio
async def test_missing_fixture_directory_log_does_not_expose_path(caplog) -> None:
    with caplog.at_level(
        logging.ERROR, logger=zip_import_fixtures.logger.name
    ), patch.object(zip_import_fixtures.Path, "exists", return_value=False):
        await zip_import_fixtures.main()

    assert "Fixture directory is unavailable" in caplog.text
    assert "secret_fixtures" not in caplog.text
