import asyncio
import base64
import ipaddress
import logging
import socket
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, TypedDict, cast
from urllib.parse import urlsplit

import aiosmtplib
from aiosmtplib.errors import (
    SMTPConnectError,
    SMTPConnectResponseError,
    SMTPConnectTimeoutError,
    SMTPServerDisconnected,
    SMTPTimeoutError,
)
from aiosmtplib.protocol import SMTPProtocol
from aiosmtplib.status import SMTPStatus

from core.config import settings

logger = logging.getLogger(__name__)

SMTP_HOST_NOT_ALLOWED = "SMTP server is not allowed"
SMTP_PORT_NOT_ALLOWED = "SMTP port is not allowed"
IMAP_HOST_NOT_ALLOWED = "IMAP server is not allowed"
IMAP_PORT_NOT_ALLOWED = "IMAP port is not allowed"
POP3_HOST_NOT_ALLOWED = "POP3 server is not allowed"
POP3_PORT_NOT_ALLOWED = "POP3 port is not allowed"
SMTP_TIMEOUT_SECONDS = 60
SMTP_EGRESS_PORTS = {25, 465, 587}
IMAP_EGRESS_PORTS = {143, 993}
POP3_EGRESS_PORTS = {110, 995}
EMAIL_HEADER_NEWLINE_ERROR = "Email header fields must not contain newlines"


@dataclass(frozen=True)
class ValidatedSmtpDestination:
    hostname: str
    port: int
    family: int
    socktype: int
    proto: int
    sockaddr: tuple[Any, ...]

@dataclass(frozen=True)
class EmailMessageParams:
    to_address: str
    subject: str
    body: str
    in_reply_to: str | None = None
    references: str | None = None

@dataclass(frozen=True)
class SmtpConfig:
    smtp_server: str
    smtp_port: int
    smtp_username: str | None = None
    smtp_password: str | None = None



def generate_oauth2_string(user: str, access_token: str) -> bytes:
    """Generates an OAuth2 string for IMAP/SMTP authentication."""
    if "\x01" in user or "\x01" in access_token:
        raise ValueError(
            "OAuth2 authentication fields must not contain SASL delimiters"
        )
    auth_string = f"user={user}\x01auth=Bearer {access_token}\x01\x01"
    return base64.b64encode(auth_string.encode("utf-8"))


def _sanitize_log_value(value: str) -> str:
    """Remove CR/LF characters from user-provided values before logging."""
    return value.replace("\r", " ").replace("\n", " ")


def _validate_email_header_value(value: str) -> str:
    """Reject CR/LF input before it can be assigned to an email header."""
    if "\r" in value or "\n" in value:
        raise ValueError(EMAIL_HEADER_NEWLINE_ERROR)
    return value


def _parse_csv_values(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _parse_allowed_ports(
    configured_ports: str, protocol_name: str, egress_ports: set[int]
) -> set[int]:
    allowed_ports = set()
    for item in _parse_csv_values(configured_ports):
        try:
            port = int(item)
        except ValueError:
            logger.warning("Ignoring invalid %s port policy entry", protocol_name)
            continue
        if port in egress_ports:
            allowed_ports.add(port)
        else:
            logger.warning("Ignoring non-%s port policy entry", protocol_name)
    return allowed_ports


def _parse_allowed_smtp_ports() -> set[int]:
    return _parse_allowed_ports(
        settings.ALLOWED_SMTP_PORTS, "SMTP", SMTP_EGRESS_PORTS
    )


def _parse_allowed_imap_ports() -> set[int]:
    return _parse_allowed_ports(
        settings.ALLOWED_IMAP_PORTS, "IMAP", IMAP_EGRESS_PORTS
    )


def _parse_allowed_pop3_ports() -> set[int]:
    return _parse_allowed_ports(
        settings.ALLOWED_POP3_PORTS, "POP3", POP3_EGRESS_PORTS
    )


def _parse_allowed_smtp_hosts() -> set[str]:
    return _parse_csv_values(settings.ALLOWED_SMTP_HOSTS)


def _parse_allowed_imap_hosts() -> set[str]:
    return _parse_csv_values(settings.ALLOWED_IMAP_HOSTS)


def _parse_allowed_pop3_hosts() -> set[str]:
    return _parse_csv_values(settings.ALLOWED_POP3_HOSTS)


def _validate_allowed_mail_host(
    normalized_host: str, allowed_hosts: set[str], host_error: str
) -> None:
    """Fail closed unless the mail host is explicitly operator-allowlisted."""
    if not allowed_hosts:
        raise ValueError(host_error)
    if any("*" in allowed_host for allowed_host in allowed_hosts):
        raise ValueError(host_error)
    if normalized_host not in allowed_hosts:
        raise ValueError(host_error)


def _validate_allowed_smtp_host(normalized_host: str) -> None:
    _validate_allowed_mail_host(
        normalized_host, _parse_allowed_smtp_hosts(), SMTP_HOST_NOT_ALLOWED
    )


def _normalize_mail_host(host: str, host_error: str) -> str:
    candidate = host.strip().lower().rstrip(".")
    if not candidate:
        raise ValueError(host_error)
    if "://" in candidate:
        parsed = urlsplit(candidate)
        candidate = (parsed.hostname or "").lower().rstrip(".")
    if any(character in candidate for character in " \t\r\n/"):
        raise ValueError(host_error)
    if not candidate or candidate in {"localhost", "localhost.localdomain"}:
        raise ValueError(host_error)
    return candidate


def _normalize_smtp_host(host: str) -> str:
    return _normalize_mail_host(host, SMTP_HOST_NOT_ALLOWED)


def _validate_public_ip_address(address: str, host_error: str) -> None:
    try:
        ip_address = ipaddress.ip_address(address)
    except ValueError as exc:
        raise ValueError(host_error) from exc
    if (
        ip_address.is_private
        or ip_address.is_loopback
        or ip_address.is_link_local
        or ip_address.is_reserved
        or ip_address.is_unspecified
        or ip_address.is_multicast
        or not ip_address.is_global
    ):
        raise ValueError(host_error)


def _is_ip_literal(candidate: str) -> bool:
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return True


def _is_legacy_numeric_ip_component(component: str) -> bool:
    if not component:
        return False
    if component.startswith("0x"):
        return len(component) > 2 and all(
            character in "0123456789abcdef" for character in component[2:]
        )
    return component.isdigit()


def _looks_like_ip_literal(candidate: str) -> bool:
    normalized_candidate = candidate.lower()
    if ":" in normalized_candidate:
        return True
    return all(
        _is_legacy_numeric_ip_component(component)
        for component in normalized_candidate.split(".")
    )


def _resolve_all_public_mail_addresses(
    mail_server: str, mail_port: int | None, host_error: str
) -> list[tuple[Any, ...]]:
    """Resolve a host and reject the entire hostname if any answer is non-global."""
    try:
        address_infos = socket.getaddrinfo(
            mail_server, mail_port, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise ValueError(host_error) from exc

    validated_address_infos = []
    for address_info in address_infos:
        sockaddr = address_info[4]
        _validate_public_ip_address(str(sockaddr[0]), host_error)
        validated_address_infos.append(address_info)
    if not validated_address_infos:
        raise ValueError(host_error)
    return validated_address_infos


def _resolve_all_public_smtp_addresses(
    smtp_server: str, smtp_port: int | None
) -> list[tuple[Any, ...]]:
    return _resolve_all_public_mail_addresses(
        smtp_server, smtp_port, SMTP_HOST_NOT_ALLOWED
    )


def validate_smtp_host(host: str, *, resolve_host: bool) -> str:
    """Validate an outbound SMTP host against operator policy and SSRF guards."""
    normalized_host = _normalize_smtp_host(host)
    _validate_allowed_smtp_host(normalized_host)

    if _is_ip_literal(normalized_host):
        _validate_public_ip_address(normalized_host, SMTP_HOST_NOT_ALLOWED)
    elif _looks_like_ip_literal(normalized_host):
        raise ValueError(SMTP_HOST_NOT_ALLOWED)
    elif resolve_host:
        _resolve_all_public_smtp_addresses(normalized_host, None)
    return normalized_host


def validate_smtp_port(port: int) -> int:
    """Validate an outbound SMTP port against operator policy."""
    allowed_ports = _parse_allowed_smtp_ports()
    if port not in allowed_ports:
        raise ValueError(SMTP_PORT_NOT_ALLOWED)
    return port


def validate_imap_host(host: str, *, resolve_host: bool) -> str:
    """Validate an outbound IMAP host against operator policy and SSRF guards."""
    normalized_host = _normalize_mail_host(host, IMAP_HOST_NOT_ALLOWED)
    _validate_allowed_mail_host(
        normalized_host, _parse_allowed_imap_hosts(), IMAP_HOST_NOT_ALLOWED
    )

    if _is_ip_literal(normalized_host):
        _validate_public_ip_address(normalized_host, IMAP_HOST_NOT_ALLOWED)
    elif _looks_like_ip_literal(normalized_host):
        raise ValueError(IMAP_HOST_NOT_ALLOWED)
    elif resolve_host:
        _resolve_all_public_mail_addresses(normalized_host, None, IMAP_HOST_NOT_ALLOWED)
    return normalized_host


def validate_imap_port(port: int) -> int:
    """Validate an outbound IMAP port against operator policy."""
    if port not in _parse_allowed_imap_ports():
        raise ValueError(IMAP_PORT_NOT_ALLOWED)
    return port


def validate_imap_destination(
    imap_server: str,
    imap_port: int,
    *,
    resolve_host: bool = True,
) -> tuple[str, int]:
    """Validate IMAP destination before any server-side network connection."""
    normalized_host = validate_imap_host(imap_server, resolve_host=resolve_host)
    return normalized_host, validate_imap_port(imap_port)


def validate_pop3_host(host: str, *, resolve_host: bool) -> str:
    """Validate an outbound POP3 host against operator policy and SSRF guards."""
    normalized_host = _normalize_mail_host(host, POP3_HOST_NOT_ALLOWED)
    _validate_allowed_mail_host(
        normalized_host, _parse_allowed_pop3_hosts(), POP3_HOST_NOT_ALLOWED
    )

    if _is_ip_literal(normalized_host):
        _validate_public_ip_address(normalized_host, POP3_HOST_NOT_ALLOWED)
    elif _looks_like_ip_literal(normalized_host):
        raise ValueError(POP3_HOST_NOT_ALLOWED)
    elif resolve_host:
        _resolve_all_public_mail_addresses(normalized_host, None, POP3_HOST_NOT_ALLOWED)
    return normalized_host


def validate_pop3_port(port: int) -> int:
    """Validate an outbound POP3 port against operator policy."""
    if port not in _parse_allowed_pop3_ports():
        raise ValueError(POP3_PORT_NOT_ALLOWED)
    return port


def validate_pop3_destination(
    pop3_server: str,
    pop3_port: int,
    *,
    resolve_host: bool = True,
) -> tuple[str, int]:
    """Validate POP3 destination before any server-side network connection."""
    normalized_host = validate_pop3_host(pop3_server, resolve_host=resolve_host)
    return normalized_host, validate_pop3_port(pop3_port)


def validate_smtp_destination(
    smtp_server: str,
    smtp_port: int,
    *,
    resolve_host: bool = True,
) -> ValidatedSmtpDestination:
    """Validate SMTP destination before any server-side network connection."""
    normalized_host = validate_smtp_host(smtp_server, resolve_host=False)
    validated_port = validate_smtp_port(smtp_port)
    if resolve_host:
        family, socktype, proto, sockaddr = _resolve_smtp_connect_address(
            normalized_host, validated_port
        )
    else:
        family, socktype, proto, sockaddr = (
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
            0,
            (normalized_host, validated_port),
        )
    return ValidatedSmtpDestination(
        hostname=normalized_host,
        port=validated_port,
        family=family,
        socktype=socktype,
        proto=proto,
        sockaddr=sockaddr,
    )


def _resolve_smtp_connect_address(
    smtp_server: str, smtp_port: int
) -> tuple[int, int, int, tuple]:
    """Resolve SMTP host once and return a globally-routable socket target."""
    fully_validated_address_infos = _resolve_all_public_smtp_addresses(
        smtp_server, smtp_port
    )
    for family, socktype, proto, _, sockaddr in fully_validated_address_infos:
        return family, socktype, proto, sockaddr
    raise ValueError(SMTP_HOST_NOT_ALLOWED)


def _validate_pinned_smtp_sockaddr(sockaddr: tuple[Any, ...]) -> None:
    """Ensure the connection target is a pre-resolved public IP, not a hostname."""
    if not sockaddr:
        raise ValueError(SMTP_HOST_NOT_ALLOWED)
    _validate_public_ip_address(str(sockaddr[0]), SMTP_HOST_NOT_ALLOWED)


async def _connect_validated_smtp_socket(
    smtp_destination: ValidatedSmtpDestination,
) -> socket.socket:
    """Connect a non-blocking socket to the pre-resolved SMTP address."""
    _validate_pinned_smtp_sockaddr(smtp_destination.sockaddr)
    smtp_socket = socket.socket(
        smtp_destination.family, smtp_destination.socktype, smtp_destination.proto
    )
    smtp_socket.setblocking(False)
    try:
        await asyncio.wait_for(
            asyncio.get_running_loop().sock_connect(
                smtp_socket, smtp_destination.sockaddr
            ),
            timeout=SMTP_TIMEOUT_SECONDS,
        )
    except Exception:
        smtp_socket.close()
        raise
    return smtp_socket


class SendEmailResult(TypedDict):
    status: str
    simulated: bool


class _PinnedImplicitTlsSMTP(aiosmtplib.SMTP):
    """SMTP client that supplies SNI when TLS starts over a pinned socket."""

    def __init__(self, *, tls_server_hostname: str, **kwargs):
        self._tls_server_hostname = tls_server_hostname
        # Keep socket-backed clients from falling back to aiosmtplib's
        # hostname="localhost" default. The socket is already connected to the
        # validated address; SNI is supplied separately during TLS setup.
        if kwargs.get("sock") is not None:
            kwargs.setdefault("port", None)
            kwargs.setdefault("socket_path", None)
            if kwargs.get("use_tls") and kwargs.get("hostname") is None:
                kwargs["hostname"] = tls_server_hostname
            else:
                kwargs.setdefault("hostname", None)
        super().__init__(**kwargs)

    def _validate_config(self) -> None:
        try:
            super()._validate_config()
        except ValueError as exc:
            if (
                self.sock is None
                or not self.use_tls
                or self.hostname != self._tls_server_hostname
                or "socket option is not compatible with hostname" not in str(exc)
            ):
                raise
            # aiosmtplib 3.x rejects hostname with sock, while 5.x requires it
            # for socket-backed TLS. Validate 3.x config with the hostname
            # hidden, then restore it for SNI and diagnostics.
            hostname = self.hostname
            self.hostname = None
            try:
                super()._validate_config()
            finally:
                self.hostname = hostname

    async def _create_connection(self, timeout: float | None):
        loop = asyncio.get_running_loop()
        smtp_socket = self.sock
        if not isinstance(smtp_socket, socket.socket) or not self.use_tls:
            return await super()._create_connection(timeout)
        smtp_socket = cast(socket.socket, smtp_socket)

        protocol = SMTPProtocol(loop=loop)
        tls_context = self._get_tls_context()
        connect_coro = loop.create_connection(
            lambda: protocol,
            sock=smtp_socket,
            ssl=tls_context,
            server_hostname=self._tls_server_hostname,
            ssl_handshake_timeout=timeout,
        )

        try:
            transport, _ = await asyncio.wait_for(connect_coro, timeout=timeout)
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise SMTPConnectTimeoutError(
                f"Timed out connecting to {self._tls_server_hostname}"
            ) from exc
        except OSError as exc:
            raise SMTPConnectError(
                f"Error connecting to {self._tls_server_hostname}: {exc}"
            ) from exc

        self.protocol = protocol
        self.transport = transport

        try:
            response = await protocol.read_response(timeout=timeout)
        except SMTPServerDisconnected as exc:
            raise SMTPConnectError(
                f"Error connecting to {self._tls_server_hostname}: {exc}"
            ) from exc
        except SMTPTimeoutError as exc:
            raise SMTPConnectTimeoutError(
                "Timed out waiting for server ready message"
            ) from exc

        if response.code != SMTPStatus.ready:
            raise SMTPConnectResponseError(response.code, response.message)

        return response


def _build_smtp_client(
    *, smtp_socket: socket.socket, smtp_server: str, smtp_port: int
) -> aiosmtplib.SMTP:
    if smtp_port == 465:
        return _PinnedImplicitTlsSMTP(
            hostname=None,
            port=None,
            sock=smtp_socket,
            timeout=SMTP_TIMEOUT_SECONDS,
            use_tls=True,
            tls_server_hostname=smtp_server,
        )
    return aiosmtplib.SMTP(
        hostname=None,
        port=None,
        sock=smtp_socket,
        timeout=SMTP_TIMEOUT_SECONDS,
        start_tls=False,
    )


async def _starttls_existing_transport(
    client: aiosmtplib.SMTP, *, tls_sni_hostname: str
) -> None:
    """Upgrade the existing pinned SMTP transport to TLS without DNS or connect."""
    await client.starttls(
        server_hostname=tls_sni_hostname,
        timeout=SMTP_TIMEOUT_SECONDS,
    )


async def _send_pinned_smtp_message(
    message: EmailMessage,
    *,
    smtp_socket: socket.socket,
    smtp_server: str,
    smtp_port: int,
    smtp_username: str | None,
    smtp_password: str | None,
) -> SendEmailResult:
    """Send through a pre-connected SMTP socket without a second DNS lookup."""
    try:
        client = _build_smtp_client(
            smtp_socket=smtp_socket,
            smtp_server=smtp_server,
            smtp_port=smtp_port,
        )
        async with client:
            if smtp_port != 465:
                await _starttls_existing_transport(client, tls_sni_hostname=smtp_server)
            if smtp_username is not None:
                await client.login(smtp_username, smtp_password or "")
            await client.send_message(message)
        return {"status": "sent", "simulated": False}
    finally:
        smtp_socket.close()


def build_email_message(
    message_params: EmailMessageParams,
    from_address: str,
) -> EmailMessage:
    """Build an outbound email message with optional threading headers."""
    message = EmailMessage()
    message["From"] = _validate_email_header_value(from_address)
    message["To"] = _validate_email_header_value(message_params.to_address)
    message["Subject"] = _validate_email_header_value(message_params.subject)
    if message_params.in_reply_to:
        message["In-Reply-To"] = _validate_email_header_value(message_params.in_reply_to)
    if message_params.references:
        message["References"] = _validate_email_header_value(message_params.references)
    message.set_content(message_params.body)
    return message


async def send_email(
    message_params: EmailMessageParams,
    smtp_config: SmtpConfig | None = None,
) -> SendEmailResult:
    """Sends an email using SMTP."""
    safe_to_address = _sanitize_log_value(message_params.to_address)

    from_address = "me@example.com"
    if smtp_config and smtp_config.smtp_username:
        from_address = smtp_config.smtp_username

    message = build_email_message(
        message_params=message_params,
        from_address=from_address,
    )

    if not smtp_config or not smtp_config.smtp_server or not smtp_config.smtp_port:
        logger.info(
            "Simulating sending email to %s (no SMTP server configured)",
            safe_to_address,
        )
        return {"status": "simulated", "simulated": True}

    smtp_destination = validate_smtp_destination(smtp_config.smtp_server, smtp_config.smtp_port)

    try:
        smtp_socket = await _connect_validated_smtp_socket(smtp_destination)
        try:
            result = await _send_pinned_smtp_message(
                message,
                smtp_socket=smtp_socket,
                smtp_server=smtp_destination.hostname,
                smtp_port=smtp_destination.port,
                smtp_username=smtp_config.smtp_username,
                smtp_password=smtp_config.smtp_password,
            )
        finally:
            smtp_socket.close()
        logger.info(
            "Successfully sent email to %s via %s",
            safe_to_address,
            smtp_destination.hostname,
        )
        return result
    except ValueError:
        raise
    except Exception as e:
        raise Exception(f"Failed to send email: {e}")
