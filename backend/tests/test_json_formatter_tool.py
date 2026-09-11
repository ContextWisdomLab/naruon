import pytest

from api.tools import (
    ANALYSIS_TEXT_MAX_CHARS,
    ExecuteRequest,
    execute_tool,
    json_formatter_handler,
    registry,
)


@pytest.mark.asyncio
async def test_json_formatter_formats_valid_json_and_preserves_unicode():
    result = await registry.invoke_tool(
        "json_formatter",
        {"json_string": '{"key":"value","안녕":"하세요"}'},
    )

    assert result == {
        "formatted_json": '{\n  "key": "value",\n  "안녕": "하세요"\n}'
    }


@pytest.mark.asyncio
async def test_json_formatter_rejects_invalid_json_syntax():
    with pytest.raises(ValueError, match="Invalid JSON string"):
        await json_formatter_handler({"json_string": '{"key":"value"'})


@pytest.mark.asyncio
@pytest.mark.parametrize("non_finite_literal", ["NaN", "Infinity", "-Infinity"])
async def test_json_formatter_rejects_non_finite_json_numbers(non_finite_literal):
    with pytest.raises(ValueError, match="Invalid JSON string"):
        await json_formatter_handler({"json_string": non_finite_literal})


@pytest.mark.asyncio
@pytest.mark.parametrize("non_finite_literal", ["NaN", "Infinity", "-Infinity"])
async def test_json_formatter_execute_contract_fails_closed(non_finite_literal):
    response = await execute_tool(
        "json_formatter",
        ExecuteRequest(parameters={"json_string": non_finite_literal}),
    )

    assert response.status == "failed"
    assert response.result is None
    assert response.message == "Invalid JSON string"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "duplicate_json",
    [
        '{"id":1,"id":2}',
        '{"outer":{"name":"first","name":"second"}}',
        r'{"a":1,"\u0061":2}',
    ],
)
async def test_json_formatter_rejects_duplicate_object_member_names(duplicate_json):
    with pytest.raises(ValueError, match="Invalid JSON string"):
        await json_formatter_handler({"json_string": duplicate_json})


@pytest.mark.asyncio
async def test_json_formatter_duplicate_member_execute_contract_fails_closed():
    response = await execute_tool(
        "json_formatter",
        ExecuteRequest(parameters={"json_string": '{"id":1,"id":2}'}),
    )

    assert response.status == "failed"
    assert response.result is None
    assert response.message == "Invalid JSON string"


@pytest.mark.asyncio
async def test_json_formatter_rejects_oversized_input_before_parsing():
    oversized = " " * (ANALYSIS_TEXT_MAX_CHARS + 1)

    with pytest.raises(
        ValueError,
        match=f"Analysis text must not exceed {ANALYSIS_TEXT_MAX_CHARS} characters",
    ):
        await json_formatter_handler({"json_string": oversized})
