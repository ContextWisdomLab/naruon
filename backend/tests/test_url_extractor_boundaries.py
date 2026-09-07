import pytest

from api.tools import url_extractor_handler


@pytest.mark.asyncio
async def test_url_extractor_preserves_boundaries_and_rejects_malformed_urls():
    """Preserve valid URL syntax while excluding prose delimiters and hostless values."""
    text = (
        "fragment https://example.com/docs#intro; "
        "tilde https://example.com/~user. "
        "unicode https://예시.한국/경로, "
        'quoted "https://example.com/quoted", '
        "parenthesized (https://example.com/docs_(v2)). "
        "hostless http:///path "
        "bad-port https://example.com:bad/path "
        "scheme-only http:// "
        "duplicate https://example.com/docs#intro "
        "malformed-dots https://example..com/path "
        "malformed-hyphen https://-example.com/path "
        "malformed-underscore https://example_test.com/path "
        "malformed-percent https://example%zz.com/path "
        "malformed-ip https://999.999.999.999/path"
    )

    result = await url_extractor_handler({"text": text})

    assert result == {
        "urls": [
            "https://example.com/docs#intro",
            "https://example.com/~user",
            "https://예시.한국/경로",
            "https://example.com/quoted",
            "https://example.com/docs_(v2)",
        ],
        "url_count": 5,
    }
