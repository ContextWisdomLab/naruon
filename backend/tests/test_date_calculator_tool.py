"""Executable contract for Naruon's deterministic date calculator tool."""

import pytest

from api.tools import registry


@pytest.mark.asyncio
async def test_date_calculator_uses_calendar_day_arithmetic() -> None:
    """Preserve leap-day and negative-offset calendar semantics."""

    assert await registry.invoke_tool(
        "date_calculator", {"base_date": "2024-02-28", "days_to_add": 1}
    ) == {"result_date": "2024-02-29"}
    assert await registry.invoke_tool(
        "date_calculator", {"base_date": "2024-03-01", "days_to_add": -1}
    ) == {"result_date": "2024-02-29"}


@pytest.mark.asyncio
@pytest.mark.parametrize("base_date", ["2024-2-29", "2024-02-9", "024-02-09"])
async def test_date_calculator_rejects_noncanonical_iso_dates(base_date: str) -> None:
    """Require the advertised four-digit-year, zero-padded YYYY-MM-DD contract."""

    with pytest.raises(ValueError, match="base_date must use YYYY-MM-DD"):
        await registry.invoke_tool(
            "date_calculator", {"base_date": base_date, "days_to_add": 0}
        )


@pytest.mark.asyncio
async def test_date_calculator_rejects_impossible_calendar_dates() -> None:
    """Separate canonical spelling from calendar validity."""

    with pytest.raises(ValueError, match="base_date must be a valid calendar date"):
        await registry.invoke_tool(
            "date_calculator", {"base_date": "2024-02-30", "days_to_add": 0}
        )


@pytest.mark.asyncio
async def test_date_calculator_rejects_out_of_range_calendar_arithmetic() -> None:
    """Fail closed instead of overflowing Python's supported calendar range."""

    with pytest.raises(
        ValueError, match="date calculation is outside the supported calendar range"
    ):
        await registry.invoke_tool(
            "date_calculator", {"base_date": "9999-12-31", "days_to_add": 1}
        )


@pytest.mark.asyncio
async def test_date_calculator_rejects_non_integer_offsets_at_registry_boundary() -> None:
    """Do not silently coerce string offsets outside the declared tool schema."""

    with pytest.raises(ValueError, match="Invalid tool parameter type"):
        await registry.invoke_tool(
            "date_calculator", {"base_date": "2024-02-29", "days_to_add": "1"}
        )
