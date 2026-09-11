from email import message_from_binary_file, message_from_bytes, policy
from email.message import Message
from pathlib import Path
import datetime
import re
from email.utils import getaddresses
from email.utils import parsedate_to_datetime
from typing import NotRequired, TypedDict
from .attachment_parser import parse_email_attachment
from .exceptions import EmailParseError
from .text_safety import strip_html_markup


class EmailData(TypedDict):
    """Parsed email data structure."""

    message_id: str
    thread_id: str | None
    sender: str
    reply_to: str | None
    recipients: str
    subject: str
    in_reply_to: str | None
    references: str | None
    date: datetime.datetime
    date_evidence: NotRequired[str]
    message_id_evidence: NotRequired[str]
    body: str
    body_content_type: NotRequired[str]
    body_parse_content: NotRequired[str]
    attachments: list[dict]


def _sanitize_nul(text: str) -> str:
    """Removes NUL characters from strings, which are invalid in PostgreSQL text fields."""
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    return text.replace("\x00", "")


def _sanitize_display_text(text: str) -> str:
    return strip_html_markup(_sanitize_nul(text))


# Mirror email.utils.formataddr's RFC 5322 display-name quoting: the specials
# that force a quoted-string, and the characters escaped inside one.
_ADDRESS_SPECIALS_RE = re.compile(r'[()<>@,;:\\".\[\]]')
_ADDRESS_QUOTED_ESCAPE_RE = re.compile(r'["\\]')


def _format_display_address(display_name: str, address: str) -> str:
    """Formats an already-decoded display name and address for storage.

    Mirrors ``email.utils.formataddr`` quoting for RFC 5322 special characters
    but keeps ``display_name`` literal instead of re-encoding a non-ASCII name
    as an RFC 2047 encoded-word. The ``From``/``To``/``Reply-To`` headers arrive
    already header-decoded (``policy.default``), and these values are stored for
    human display, not re-emitted as message headers, so ``formataddr`` would
    corrupt a decoded name (e.g. Korean) back into ``=?utf-8?b?...?=``.
    """
    if not display_name:
        return address
    if _ADDRESS_SPECIALS_RE.search(display_name):
        escaped_name = _ADDRESS_QUOTED_ESCAPE_RE.sub(r"\\\g<0>", display_name)
        return f'"{escaped_name}" <{address}>'
    return f"{display_name} <{address}>"


def _sanitize_address_display_text(text: str) -> str:
    sanitized_parts: list[str] = []
    for display_name, address in getaddresses([text]):
        safe_display_name = _sanitize_display_text(display_name).strip()
        safe_address = _sanitize_nul(address).strip()
        if safe_address:
            sanitized_parts.append(
                _format_display_address(safe_display_name, safe_address)
            )
        elif safe_display_name:
            sanitized_parts.append(safe_display_name)
    if sanitized_parts:
        return ", ".join(sanitized_parts)
    return _sanitize_display_text(text)


def _process_multipart_body(msg: Message) -> tuple[str, str, list[dict]]:
    plain_body = ""
    html_body = ""
    attachments = []

    for part in msg.walk():
        content_type = part.get_content_type()
        filename = part.get_filename()
        # Skip attachments
        if filename:
            parsed_attachment = parse_email_attachment(
                filename=filename,
                content_type=content_type,
                raw_content=_attachment_part_content(part),
            )
            attachments.append(
                {
                    "filename": parsed_attachment.filename,
                    "content": parsed_attachment.content,
                    "content_type": parsed_attachment.content_type,
                    "parse_content": parsed_attachment.parse_content,
                    "parse_content_type": parsed_attachment.parse_content_type,
                    "parser_key": parsed_attachment.parser_key,
                    "parse_status": parsed_attachment.parse_status,
                    "parse_error_code": parsed_attachment.parse_error_code,
                }
            )
            continue

        if content_type == "text/plain":
            part_content = part.get_content()
            if isinstance(part_content, str):
                plain_body += part_content
        elif content_type == "text/html":
            part_content = part.get_content()
            if isinstance(part_content, str):
                html_body += part_content
    return plain_body, html_body, attachments


def _attachment_part_content(part: Message) -> object:
    try:
        return part.get_content()
    except (LookupError, TypeError, ValueError):
        payload = part.get_payload(decode=True)
        return payload if payload is not None else ""


def _process_singlepart_body(msg: Message) -> tuple[str, str, list[dict]]:
    plain_body = ""
    html_body = ""
    content_type = msg.get_content_type()
    part_content = msg.get_content()
    if isinstance(part_content, str):
        if content_type == "text/html":
            html_body = part_content
        else:
            plain_body = part_content
    return plain_body, html_body, []


def _extract_body_and_attachments(msg: Message) -> tuple[str, str, list[dict]]:
    if msg.is_multipart():
        plain_body, html_body, attachments = _process_multipart_body(msg)
    else:
        plain_body, html_body, attachments = _process_singlepart_body(msg)

    if plain_body:
        return plain_body, "text/plain", attachments
    return html_body, "text/html" if html_body else "text/plain", attachments


def _extract_date(msg: Message) -> tuple[datetime.datetime, str]:
    date_header = msg.get("Date")
    parsed_date = None
    evidence = "missing"
    if date_header:
        try:
            parsed_date = parsedate_to_datetime(date_header)
            evidence = "parsed" if parsed_date is not None else "invalid"
        except (TypeError, ValueError):
            parsed_date = None
            evidence = "invalid"

    if not parsed_date:
        parsed_date = datetime.datetime.now(datetime.timezone.utc)
    elif parsed_date.tzinfo is None:
        # RFC 5322 section 3.3: a "-0000" zone means the time zone is unknown,
        # for which parsedate_to_datetime returns a naive datetime. Every other
        # branch here yields a timezone-aware datetime, and mixing naive with
        # aware datetimes raises TypeError on comparison/sorting and misbinds the
        # instant when stored in a timestamptz column. Treat the unknown zone as
        # UTC so the returned value is always timezone-aware.
        parsed_date = parsed_date.replace(tzinfo=datetime.timezone.utc)
    return parsed_date, evidence


def _extract_thread_id(msg: Message, message_id: str) -> str | None:
    references = msg.get("References")  # O3: email threading support

    if references:
        refs = references.split(None, 1)
        if refs:
            return _sanitize_nul(refs[0])

    in_reply_to = msg.get("In-Reply-To")
    if in_reply_to:
        in_reply_to_list = in_reply_to.split(None, 1)
        if in_reply_to_list:
            return _sanitize_nul(in_reply_to_list[0])

    return message_id


def _message_to_email_data(msg: Message) -> EmailData:
    body, body_content_type, attachments = _extract_body_and_attachments(msg)
    parsed_date, date_evidence = _extract_date(msg)
    message_id = _sanitize_nul(msg.get("Message-ID", ""))
    thread_id = _extract_thread_id(msg, message_id)

    return {
        "message_id": message_id,
        "thread_id": thread_id,
        "sender": _sanitize_address_display_text(msg.get("From", "")),
        "reply_to": (
            _sanitize_address_display_text(msg.get("Reply-To", ""))
            if msg.get("Reply-To")
            else None
        ),
        "recipients": _sanitize_address_display_text(msg.get("To", "")),
        "subject": _sanitize_display_text(msg.get("Subject", "")),
        "in_reply_to": (
            _sanitize_nul(msg.get("In-Reply-To", ""))
            if msg.get("In-Reply-To")
            else None
        ),
        "references": (
            _sanitize_nul(msg.get("References", "")) if msg.get("References") else None
        ),
        "date": parsed_date,
        "date_evidence": date_evidence,
        "message_id_evidence": "embedded" if message_id else "missing",
        "body": _sanitize_display_text(body),
        "body_content_type": body_content_type,
        "body_parse_content": _sanitize_nul(body),
        "attachments": attachments,
    }


def parse_eml(file_path: str | Path) -> EmailData:
    """Parses an EML file and extracts email metadata and body.

    Raises:
        EmailParseError: If there is an issue reading the file.
    """
    try:
        with open(file_path, "rb") as f:
            msg = message_from_binary_file(f, policy=policy.default)
    except OSError as e:
        raise EmailParseError(f"Failed to read file {file_path}: {e}") from e

    return _message_to_email_data(msg)


def parse_eml_bytes(content: bytes) -> EmailData:
    """Parses EML bytes fetched from a provider."""
    try:
        msg = message_from_bytes(content, policy=policy.default)
    except Exception as e:
        raise EmailParseError("Failed to parse provider email bytes") from e

    return _message_to_email_data(msg)
