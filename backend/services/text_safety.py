import html
import string
from html.parser import HTMLParser

_RAW_TEXT_TAGS = {"script", "style", "template"}
_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "div",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tr",
    "ul",
}
_LOCAL_PART_CHARACTERS = set(
    string.ascii_letters + string.digits + ".!#$%&*+-/=?^_`{|}~"
)
_DOMAIN_CHARACTERS = set(string.ascii_letters + string.digits + ".-")
# Browser-recognized tags must win before preserving mixed-case bracketed labels.
# Keep legacy tags here so entity-encoded or mixed-case HTML still fails closed.
_KNOWN_HTML_TAGS = (
    _RAW_TEXT_TAGS
    | _BLOCK_TAGS
    | {
        "a",
        "abbr",
        "acronym",
        "applet",
        "area",
        "audio",
        "b",
        "base",
        "basefont",
        "bdi",
        "bdo",
        "bgsound",
        "big",
        "blink",
        "body",
        "button",
        "canvas",
        "caption",
        "center",
        "code",
        "col",
        "colgroup",
        "command",
        "content",
        "data",
        "datalist",
        "dd",
        "del",
        "details",
        "dfn",
        "dialog",
        "dir",
        "dl",
        "dt",
        "em",
        "embed",
        "fieldset",
        "figcaption",
        "figure",
        "font",
        "frame",
        "frameset",
        "form",
        "head",
        "hr",
        "html",
        "i",
        "iframe",
        "img",
        "input",
        "ins",
        "isindex",
        "kbd",
        "keygen",
        "label",
        "legend",
        "listing",
        "link",
        "map",
        "mark",
        "marquee",
        "menu",
        "menuitem",
        "math",
        "meta",
        "meter",
        "nav",
        "nobr",
        "noembed",
        "noframes",
        "noscript",
        "object",
        "optgroup",
        "option",
        "output",
        "param",
        "picture",
        "plaintext",
        "portal",
        "progress",
        "q",
        "rb",
        "rp",
        "rt",
        "rtc",
        "ruby",
        "s",
        "samp",
        "select",
        "shadow",
        "slot",
        "small",
        "source",
        "span",
        "strike",
        "strong",
        "sub",
        "summary",
        "sup",
        "svg",
        "tbody",
        "td",
        "textarea",
        "tfoot",
        "th",
        "thead",
        "time",
        "title",
        "track",
        "tt",
        "u",
        "var",
        "video",
        "wbr",
        "xmp",
    }
)


def _decode_entities(value: str) -> str:
    decoded = value
    for _ in range(3):
        next_value = html.unescape(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded


def _looks_like_angle_email(value: str) -> bool:
    if value.count("@") != 1 or any(character.isspace() for character in value):
        return False
    if any(character in value for character in "<>\"'"):
        return False

    local_part, domain = value.rsplit("@", 1)
    if not local_part or not domain or "." not in domain:
        return False
    if any(character not in _LOCAL_PART_CHARACTERS for character in local_part):
        return False
    if any(character not in _DOMAIN_CHARACTERS for character in domain):
        return False
    if domain.startswith((".", "-")) or domain.endswith((".", "-")):
        return False
    if ".." in domain:
        return False
    return True


def _mask_angle_emails(value: str) -> tuple[str, dict[str, str]]:
    placeholders: dict[str, str] = {}
    parts: list[str] = []
    cursor = 0

    while cursor < len(value):
        start = value.find("<", cursor)
        if start == -1:
            parts.append(value[cursor:])
            break

        end = value.find(">", start + 1)
        if end == -1:
            parts.append(value[cursor:])
            break

        candidate = value[start + 1 : end]
        before_is_boundary = start == 0 or value[start - 1].isspace()
        after_is_boundary = (
            end + 1 == len(value)
            or value[end + 1].isspace()
            or value[end + 1] in ",.;:)]}"
        )
        if (
            _looks_like_angle_email(candidate)
            and before_is_boundary
            and after_is_boundary
        ):
            token = f"\ue000email{len(placeholders)}\ue001"
            placeholders[token] = value[start : end + 1]
            parts.append(value[cursor:start])
            parts.append(token)
            cursor = end + 1
            continue

        parts.append(value[cursor : start + 1])
        cursor = start + 1

    return "".join(parts), placeholders


def _skip_spaces(text: str, start: int) -> int:
    cursor = start
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    return cursor


def _check_html_tag_at(decoded: str, cursor: int) -> tuple[bool, int]:
    tag_start = cursor + 1

    if decoded.startswith("!--", tag_start):
        return True, 0

    if decoded[tag_start].isspace():
        space_cursor = _skip_spaces(decoded, tag_start)
        if space_cursor >= len(decoded) or decoded[space_cursor] != "/":
            return False, cursor + 1
        tag_start = space_cursor

    if decoded[tag_start] in {"!", "?"}:
        return True, 0

    if decoded[tag_start] == "/":
        tag_start = _skip_spaces(decoded, tag_start + 1)

    closing = decoded.find(">", tag_start + 1)
    if tag_start < len(decoded) and decoded[tag_start].isalpha():
        tag_content = decoded[
            tag_start : closing if closing != -1 else None
        ].strip()
        next_cursor = closing + 1 if closing != -1 else len(decoded)

        if _looks_like_angle_email(tag_content):
            return False, next_cursor
        if _is_tag_like_segment(tag_content):
            return True, 0
        return False, next_cursor

    return False, cursor + 1


def contains_html_markup(value: str) -> bool:
    decoded = _decode_entities(value)
    cursor = 0
    while cursor < len(decoded):
        if decoded[cursor] != "<":
            cursor += 1
            continue

        if cursor + 1 >= len(decoded):
            return False

        found_markup, next_cursor = _check_html_tag_at(decoded, cursor)
        if found_markup:
            return True
        cursor = next_cursor

    return False


def _split_tag_candidate(value: str) -> tuple[str, str]:
    raw_tag_name, remainder = _split_raw_tag_candidate(value)
    return raw_tag_name.lower(), remainder


def _split_raw_tag_candidate(value: str) -> tuple[str, str]:
    tag_name_chars: list[str] = []
    cursor = 0
    while cursor < len(value):
        character = value[cursor]
        if character.isalnum() or character in {":", "-"}:
            tag_name_chars.append(character)
            cursor += 1
            continue
        break
    return "".join(tag_name_chars), value[cursor:]


def _is_preservable_bracketed_label(value: str) -> bool:
    raw_tag_name, remainder = _split_raw_tag_candidate(value.strip())
    if not raw_tag_name or remainder:
        return False
    normalized = raw_tag_name.lower()
    return (
        normalized not in _KNOWN_HTML_TAGS
        and "-" not in raw_tag_name
        and ":" not in raw_tag_name
        and any(character.isupper() for character in raw_tag_name)
    )


def _unknown_tag_segment_has_unsafe_markers(tag_name: str, remainder: str) -> bool:
    if "-" in tag_name or ":" in tag_name:
        return True

    normalized_remainder = remainder.strip()
    if not normalized_remainder or normalized_remainder == "/":
        return True
    if any(character in normalized_remainder for character in {'"', "'", "`", "="}):
        return True
    tokens = normalized_remainder.replace("/", " ").split()
    return any(token.lower().startswith("on") for token in tokens)


def _is_tag_like_segment(value: str) -> bool:
    if not value or value[0].isspace():
        return False
    candidate = value.strip()
    if not candidate:
        return False
    if candidate.startswith("!--") or candidate[0] in {"!", "?"}:
        return True
    if candidate[0] == "/":
        candidate = candidate[1:].lstrip()
    if not candidate or not candidate[0].isalpha():
        return False
    tag_name, remainder = _split_tag_candidate(candidate)
    if tag_name in _KNOWN_HTML_TAGS:
        return True
    if _is_preservable_bracketed_label(candidate):
        return False
    return _unknown_tag_segment_has_unsafe_markers(tag_name, remainder)


def _preserve_unknown_start_tag(raw_start_tag: str | None, attrs) -> bool:
    if raw_start_tag is None:
        return False
    tag_text = raw_start_tag.strip()
    if not tag_text.startswith("<") or not tag_text.endswith(">"):
        return False
    candidate = tag_text[1:-1].strip().rstrip("/").strip()
    if not _is_preservable_bracketed_label(candidate):
        return False
    for name, value in attrs:
        if name.lower().startswith("on") or value is not None:
            return False
    return True


def _strip_tag_like_segments(value: str) -> str:
    parts: list[str] = []
    cursor = 0
    while cursor < len(value):
        start = value.find("<", cursor)
        if start == -1:
            parts.append(value[cursor:])
            break

        end = value.find(">", start + 1)
        if end == -1:
            candidate = value[start + 1 :]
            parts.append(value[cursor:start])
            if not _is_tag_like_segment(candidate):
                parts.append(value[start:])
            break

        parts.append(value[cursor:start])
        candidate = value[start + 1 : end]
        if not _is_tag_like_segment(candidate):
            parts.append(value[start : end + 1])
        cursor = end + 1
    return "".join(parts)


def _normalize_plain_text(value: str) -> str:
    lines = []
    for line in value.splitlines():
        normalized_line = " ".join(_strip_tag_like_segments(line).split())
        if normalized_line:
            lines.append(normalized_line)
    return "\n".join(lines).strip()


class _PlainTextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._raw_text_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        normalized = tag.lower()
        if normalized in _RAW_TEXT_TAGS:
            self._raw_text_depth += 1
            return
        if normalized in _BLOCK_TAGS:
            self._parts.append("\n")
            return
        if self._raw_text_depth == 0 and _preserve_unknown_start_tag(
            self.get_starttag_text(), attrs
        ):
            self._parts.append(self.get_starttag_text() or f"<{tag}>")

    def handle_startendtag(self, tag: str, attrs) -> None:
        normalized = tag.lower()
        if normalized in _RAW_TEXT_TAGS or normalized in _BLOCK_TAGS:
            return
        if self._raw_text_depth == 0 and _preserve_unknown_start_tag(
            self.get_starttag_text(), attrs
        ):
            self._parts.append(self.get_starttag_text() or f"<{tag} />")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in _RAW_TEXT_TAGS:
            self._raw_text_depth = max(0, self._raw_text_depth - 1)
            return
        if normalized in _BLOCK_TAGS:
            self._parts.append("\n")
            return

    def handle_data(self, data: str) -> None:
        if self._raw_text_depth == 0:
            self._parts.append(_strip_tag_like_segments(data))

    def get_text(self) -> str:
        return _normalize_plain_text("".join(self._parts))


def strip_html_markup(value: str) -> str:
    if "<" not in value and "&" not in value:
        return _normalize_plain_text(value)

    decoded = _decode_entities(value)
    masked, placeholders = _mask_angle_emails(decoded)
    # HTMLParser can expose the tail of the malformed ``<!-->`` opener as
    # literal data. Normalize that opener into an ignored comment boundary
    # without deleting legitimate ``-->`` text elsewhere in user content.
    masked = masked.replace("<!-->", "<!--")
    parser = _PlainTextHTMLParser()
    parser.feed(masked)
    parser.close()
    text = parser.get_text()

    cleaned_lines = []
    for line in text.splitlines():
        cleaned_lines.append(_strip_tag_like_segments(line))
    text = "\n".join(cleaned_lines).strip()

    for token, original in placeholders.items():
        text = text.replace(token, original)
    return text
