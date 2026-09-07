import pytest

from api.tools import url_extractor_handler


@pytest.mark.asyncio
async def test_url_extractor_preserves_boundaries_and_rejects_malformed_urls():
    """Preserve valid URL syntax while excluding prose delimiters and malformed hosts."""
    text = (
        "fragment https://example.com/docs#intro; "
        "tilde https://example.com/~user. "
        "unicode https://예시.한국/경로, "
        'quoted "https://example.com/quoted", '
        "parenthesized (https://example.com/docs_(v2)). "
        "hostless http:///path "
        "missing-host https://:443/path "
        "userinfo-without-host https://user@:443/path "
        "bad-port https://example.com:bad/path "
        "scheme-only http:// "
        "duplicate https://example.com/docs#intro"
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
