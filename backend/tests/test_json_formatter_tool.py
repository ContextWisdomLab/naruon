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
@pytest.mark.parametrize(
    "surrogate_json",
    [
        r'"\ud800"',
        r'"\udc00"',
        r'{"\ud800":"value"}',
    ],
)
async def test_json_formatter_rejects_unpaired_unicode_surrogates(surrogate_json):
    with pytest.raises(ValueError, match="Invalid JSON string"):
        await json_formatter_handler({"json_string": surrogate_json})


@pytest.mark.asyncio
async def test_json_formatter_accepts_valid_unicode_surrogate_pair():
    result = await json_formatter_handler({"json_string": r'"\ud83d\ude00"'})

    assert result == {"formatted_json": '"😀"'}


@pytest.mark.asyncio
async def test_json_formatter_unpaired_surrogate_execute_contract_fails_closed():
    response = await execute_tool(
        "json_formatter",
        ExecuteRequest(parameters={"json_string": r'"\ud800"'}),
    )

    assert response.status == "failed"
    assert response.result is None
    assert response.message == "Invalid JSON string"


@pytest.mark.asyncio
async def test_json_formatter_preserves_exact_number_lexemes():
    source = (
        '{"precise":0.123456789012345678901234567890,'
        '"tiny":1e-400,"negative_zero":-0,'
        '"large":12345678901234567890.123456789}'
    )

    result = await json_formatter_handler({"json_string": source})

    assert result == {
        "formatted_json": (
            "{\n"
            '  "precise": 0.123456789012345678901234567890,\n'
            '  "tiny": 1e-400,\n'
            '  "negative_zero": -0,\n'
            '  "large": 12345678901234567890.123456789\n'
            "}"
        )
    }


@pytest.mark.asyncio
async def test_json_formatter_exact_numbers_survive_public_execution_boundary():
    source = '{"value":1.234567890123456789e+100}'

    response = await execute_tool(
        "json_formatter",
        ExecuteRequest(parameters={"json_string": source}),
    )

    assert response.status == "success"
    assert response.result == {
        "formatted_json": '{\n  "value": 1.234567890123456789e+100\n}'
    }


@pytest.mark.asyncio
async def test_json_formatter_preserves_standard_scalar_and_empty_container_types():
    source = '{"values":[true,false,null,1,1.25],"object":{},"array":[]}'

    result = await json_formatter_handler({"json_string": source})

    assert result == {
        "formatted_json": (
            "{\n"
            '  "values": [\n'
            "    true,\n"
            "    false,\n"
            "    null,\n"
            "    1,\n"
            "    1.25\n"
            "  ],\n"
            '  "object": {},\n'
            '  "array": []\n'
            "}"
        )
    }


@pytest.mark.asyncio
async def test_json_formatter_rejects_recursion_limit_input():
    deeply_nested = "[" * 10_000 + "0" + "]" * 10_000
    assert len(deeply_nested) <= ANALYSIS_TEXT_MAX_CHARS

    with pytest.raises(ValueError, match="Invalid JSON string"):
        await json_formatter_handler({"json_string": deeply_nested})


@pytest.mark.asyncio
async def test_json_formatter_recursion_limit_execute_contract_fails_closed():
    deeply_nested = "[" * 10_000 + "0" + "]" * 10_000
    response = await execute_tool(
        "json_formatter",
        ExecuteRequest(parameters={"json_string": deeply_nested}),
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


@pytest.mark.asyncio
async def test_json_formatter_rejects_pretty_output_amplification_beyond_ceiling():
    source = "[" * 100 + ",".join(["0"] * 600) + "]" * 100
    assert len(source) < ANALYSIS_TEXT_MAX_CHARS

    with pytest.raises(
        ValueError,
        match=f"Formatted JSON must not exceed {ANALYSIS_TEXT_MAX_CHARS} characters",
    ):
        await json_formatter_handler({"json_string": source})


@pytest.mark.asyncio
async def test_json_formatter_output_amplification_fails_closed_at_public_boundary():
    source = "[" * 100 + ",".join(["0"] * 600) + "]" * 100
    response = await execute_tool(
        "json_formatter",
        ExecuteRequest(parameters={"json_string": source}),
    )

    assert response.status == "failed"
    assert response.result is None
    assert response.message == (
        f"Formatted JSON must not exceed {ANALYSIS_TEXT_MAX_CHARS} characters"
    )
