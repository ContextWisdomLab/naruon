import asyncio
import inspect
import socket

import pytest
import services.email_client as email_client
from runner.local_mail_adapters import LocalMailAccountConfig, LocalMailAdapters

import os

TEST_SMTP_PASSWORD = os.environ.get("TEST_SMTP_PASSWORD", "dummy-smtp-password")


def _make_socket() -> socket.socket:
    return socket.socket(socket.AF_INET, socket.SOCK_STREAM)


@pytest.mark.asyncio
@pytest.mark.parametrize("send_path", ["direct_send", "registered_connector"])
async def test_smtp_connect_cancellation_closes_socket(monkeypatch, send_path):
    """Cancelling either sender must close its real socket before returning."""
    monkeypatch.setattr(email_client.settings, "ALLOWED_SMTP_HOSTS", "smtp.example.com")
    monkeypatch.setattr(
        email_client.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 587))
        ],
    )
    connect_started = asyncio.Event()
    connect_pending = asyncio.Event()
    captured_sockets = []

    async def pending_connect(smtp_socket, socket_address):
        assert socket_address == ("8.8.8.8", 587)
        captured_sockets.append(smtp_socket)
        connect_started.set()
        await connect_pending.wait()

    monkeypatch.setattr(asyncio.get_running_loop(), "sock_connect", pending_connect)
    smtp_config = email_client.SmtpConfig(
        smtp_server="smtp.example.com",
        smtp_port=587,
        smtp_username="sender@example.com",
        smtp_password="unit-test-value",
    )
    if send_path == "direct_send":
        send_operation = email_client.send_email(
            email_client.EmailMessageParams("recipient@example.com", "Subject", "Body"),
            smtp_config,
        )
    else:
        mail_adapters = LocalMailAdapters([
            LocalMailAccountConfig(
                account="test_account",
                user_id="test_user",
                smtp_server=smtp_config.smtp_server,
                smtp_port=smtp_config.smtp_port,
                smtp_username=smtp_config.smtp_username,
                smtp_password=smtp_config.smtp_password,
            )
        ])
        send_operation = mail_adapters.send_smtp({
            "account": "test_account",
            "to": "recipient@example.com",
            "subject": "Subject",
            "body": "Body",
        })
    send_task = asyncio.create_task(send_operation)
    try:
        await asyncio.wait_for(connect_started.wait(), timeout=5)
        send_task.cancel("send cancelled")
        with pytest.raises(asyncio.CancelledError, match="send cancelled"):
            await send_task
        assert len(captured_sockets) == 1
        assert captured_sockets[0].fileno() == -1
    finally:
        send_task.cancel()
        await asyncio.gather(send_task, return_exceptions=True)
        for smtp_socket in captured_sockets:
            smtp_socket.close()


def test_smtp_host_policy_denies_empty_allowlist_before_dns(monkeypatch):
    monkeypatch.setattr(email_client.settings, "ALLOWED_SMTP_HOSTS", "")

    def fail_getaddrinfo(*args, **kwargs):
        raise AssertionError("empty SMTP allowlist must fail before DNS resolution")

    monkeypatch.setattr(email_client.socket, "getaddrinfo", fail_getaddrinfo)

    with pytest.raises(ValueError, match=email_client.SMTP_HOST_NOT_ALLOWED):
        email_client.validate_smtp_host("smtp.example.com", resolve_host=True)


def test_smtp_allowed_host_helper_fails_closed_when_allowlist_empty(monkeypatch):
    monkeypatch.setattr(email_client.settings, "ALLOWED_SMTP_HOSTS", "")

    with pytest.raises(ValueError, match=email_client.SMTP_HOST_NOT_ALLOWED):
        email_client._validate_allowed_smtp_host("smtp.example.com")


def test_smtp_host_policy_keeps_empty_allowlist_guard_explicit():
    source = inspect.getsource(email_client._validate_allowed_mail_host)

    assert "if not allowed_hosts:" in source
    assert "if normalized_host not in allowed_hosts:" in source


def test_smtp_host_policy_rejects_wildcard_allowlist_entry(monkeypatch):
    monkeypatch.setattr(
        email_client.settings,
        "ALLOWED_SMTP_HOSTS",
        "smtp.example.com,*",
    )
    monkeypatch.setattr(
        email_client.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 587))
        ],
    )

    with pytest.raises(ValueError, match=email_client.SMTP_HOST_NOT_ALLOWED):
        email_client.validate_smtp_host("smtp.example.com", resolve_host=True)


def test_smtp_host_policy_normalizes_url_form_before_slash_filter(monkeypatch):
    monkeypatch.setattr(email_client.settings, "ALLOWED_SMTP_HOSTS", "smtp.example.com")

    normalized_host = email_client.validate_smtp_host(
        "smtp://SMTP.EXAMPLE.COM.",
        resolve_host=False,
    )

    assert normalized_host == "smtp.example.com"


def test_smtp_port_policy_rejects_configured_non_smtp_ports(monkeypatch):
    monkeypatch.setattr(email_client.settings, "ALLOWED_SMTP_PORTS", "465,587,80")

    with pytest.raises(ValueError, match=email_client.SMTP_PORT_NOT_ALLOWED):
        email_client.validate_smtp_port(80)


def test_smtp_ip_policy_uses_explicit_ssrf_denylists():
    source = inspect.getsource(email_client._validate_public_ip_address)

    for guard in (
        "is_private",
        "is_loopback",
        "is_link_local",
        "is_reserved",
        "is_unspecified",
        "is_multicast",
    ):
        assert guard in source


def test_smtp_control_plane_hostname_is_resolved_before_ip_policy(monkeypatch):
    monkeypatch.setattr(email_client.settings, "ALLOWED_SMTP_HOSTS", "naruon.net")
    monkeypatch.setattr(email_client.settings, "CONTROL_PLANE_DOMAIN", "naruon.net")
    monkeypatch.setattr(
        email_client.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 587))
        ],
    )
    original_validate_public_ip_address = email_client._validate_public_ip_address
    validated_addresses = []

    def fake_validate_public_ip_address(address, host_error):
        validated_addresses.append(address)
        if address == "naruon.net":
            raise AssertionError("raw hostnames must be resolved before IP checks")
        original_validate_public_ip_address(address, host_error)

    monkeypatch.setattr(
        email_client,
        "_validate_public_ip_address",
        fake_validate_public_ip_address,
    )

    with pytest.raises(ValueError, match=email_client.SMTP_HOST_NOT_ALLOWED):
        email_client.validate_smtp_host("naruon.net", resolve_host=True)

    assert validated_addresses == ["127.0.0.1"]


def test_smtp_host_rejects_mixed_public_and_private_dns_answers(monkeypatch):
    monkeypatch.setattr(email_client.settings, "ALLOWED_SMTP_HOSTS", "smtp.example.com")
    monkeypatch.setattr(
        email_client.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 587)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 587)),
        ],
    )

    with pytest.raises(ValueError, match=email_client.SMTP_HOST_NOT_ALLOWED):
        email_client.validate_smtp_host("smtp.example.com", resolve_host=True)


@pytest.mark.parametrize(
    "numeric_host",
    ["2130706433", "0x7f000001", "0177.0.0.1", "127001"],
)
def test_smtp_host_rejects_legacy_numeric_ip_literals_before_dns(
    monkeypatch, numeric_host
):
    monkeypatch.setattr(email_client.settings, "ALLOWED_SMTP_HOSTS", numeric_host)

    def fail_getaddrinfo(*args, **kwargs):
        raise AssertionError("legacy numeric SMTP host must fail before DNS")

    monkeypatch.setattr(email_client.socket, "getaddrinfo", fail_getaddrinfo)

    with pytest.raises(ValueError, match=email_client.SMTP_HOST_NOT_ALLOWED):
        email_client.validate_smtp_host(numeric_host, resolve_host=True)


@pytest.mark.parametrize(
    ("protocol_name", "allowed_setting", "validator", "host_error"),
    [
        (
            "IMAP",
            "ALLOWED_IMAP_HOSTS",
            email_client.validate_imap_host,
            email_client.IMAP_HOST_NOT_ALLOWED,
        ),
        (
            "POP3",
            "ALLOWED_POP3_HOSTS",
            email_client.validate_pop3_host,
            email_client.POP3_HOST_NOT_ALLOWED,
        ),
    ],
)
def test_inbound_mail_hosts_reject_legacy_numeric_ip_literals_before_dns(
    monkeypatch,
    protocol_name,
    allowed_setting,
    validator,
    host_error,
):
    numeric_host = "2130706433"
    monkeypatch.setattr(email_client.settings, allowed_setting, numeric_host)

    def fail_getaddrinfo(*args, **kwargs):
        raise AssertionError(
            f"legacy numeric {protocol_name} host must fail before DNS"
        )

    monkeypatch.setattr(email_client.socket, "getaddrinfo", fail_getaddrinfo)

    with pytest.raises(ValueError, match=host_error):
        validator(numeric_host, resolve_host=True)


def test_smtp_destination_rejects_mixed_public_and_private_dns_answers(monkeypatch):
    monkeypatch.setattr(email_client.settings, "ALLOWED_SMTP_HOSTS", "smtp.example.com")
    monkeypatch.setattr(email_client.settings, "ALLOWED_SMTP_PORTS", "587")
    monkeypatch.setattr(
        email_client.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 587)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 587)),
        ],
    )

    with pytest.raises(ValueError, match=email_client.SMTP_HOST_NOT_ALLOWED):
        email_client.validate_smtp_destination("smtp.example.com", 587)


def test_imap_host_policy_denies_empty_allowlist_before_dns(monkeypatch):
    monkeypatch.setattr(email_client.settings, "ALLOWED_IMAP_HOSTS", "")

    def fail_getaddrinfo(*args, **kwargs):
        raise AssertionError("empty IMAP allowlist must fail before DNS resolution")

    monkeypatch.setattr(email_client.socket, "getaddrinfo", fail_getaddrinfo)

    with pytest.raises(ValueError, match=email_client.IMAP_HOST_NOT_ALLOWED):
        email_client.validate_imap_destination("imap.example.com", 993)


def test_pop3_host_policy_denies_empty_allowlist_before_dns(monkeypatch):
    monkeypatch.setattr(email_client.settings, "ALLOWED_POP3_HOSTS", "")

    def fail_getaddrinfo(*args, **kwargs):
        raise AssertionError("empty POP3 allowlist must fail before DNS resolution")

    monkeypatch.setattr(email_client.socket, "getaddrinfo", fail_getaddrinfo)

    with pytest.raises(ValueError, match=email_client.POP3_HOST_NOT_ALLOWED):
        email_client.validate_pop3_destination("pop3.example.com", 995)


def test_imap_host_policy_rejects_wildcard_allowlist_entry(monkeypatch):
    monkeypatch.setattr(
        email_client.settings,
        "ALLOWED_IMAP_HOSTS",
        "imap.example.com,*",
    )

    with pytest.raises(ValueError, match=email_client.IMAP_HOST_NOT_ALLOWED):
        email_client.validate_imap_destination(
            "imap.example.com", 993, resolve_host=False
        )


def test_imap_destination_rejects_non_imap_port(monkeypatch):
    monkeypatch.setattr(email_client.settings, "ALLOWED_IMAP_HOSTS", "imap.example.com")
    monkeypatch.setattr(email_client.settings, "ALLOWED_IMAP_PORTS", "993,22")

    with pytest.raises(ValueError, match=email_client.IMAP_PORT_NOT_ALLOWED):
        email_client.validate_imap_destination(
            "imap.example.com", 22, resolve_host=False
        )


def test_pop3_destination_rejects_non_pop3_port(monkeypatch):
    monkeypatch.setattr(email_client.settings, "ALLOWED_POP3_HOSTS", "pop3.example.com")
    monkeypatch.setattr(email_client.settings, "ALLOWED_POP3_PORTS", "995,22")

    with pytest.raises(ValueError, match=email_client.POP3_PORT_NOT_ALLOWED):
        email_client.validate_pop3_destination(
            "pop3.example.com", 22, resolve_host=False
        )


def test_pop3_host_policy_rejects_wildcard_allowlist_entry(monkeypatch):
    monkeypatch.setattr(
        email_client.settings,
        "ALLOWED_POP3_HOSTS",
        "pop3.example.com,*",
    )

    with pytest.raises(ValueError, match=email_client.POP3_HOST_NOT_ALLOWED):
        email_client.validate_pop3_destination(
            "pop3.example.com", 995, resolve_host=False
        )


def test_pop3_destination_rejects_private_dns_answer(monkeypatch):
    monkeypatch.setattr(email_client.settings, "ALLOWED_POP3_HOSTS", "pop3.example.com")
    monkeypatch.setattr(email_client.settings, "ALLOWED_POP3_PORTS", "995")
    monkeypatch.setattr(
        email_client.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.10", 995))
        ],
    )

    with pytest.raises(ValueError, match=email_client.POP3_HOST_NOT_ALLOWED):
        email_client.validate_pop3_destination("pop3.example.com", 995)


def test_smtp_connect_address_does_not_select_unvalidated_first_dns_answer():
    source = inspect.getsource(email_client._resolve_smtp_connect_address)

    assert "address_infos[0]" not in source


def test_smtp_connect_address_uses_all_answer_validation_helper():
    source = inspect.getsource(email_client._resolve_smtp_connect_address)

    assert "_resolve_all_public_smtp_addresses" in source
    assert "connect_address = connect_address or" not in source


class FakeSmtpClient:
    def __init__(self, *, fail_send=False):
        self.fail_send = fail_send
        self.entered = False
        self.exited = False
        self.starttls_hostname = None
        self.login_args = None
        self.sent_message = None

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.exited = True

    async def starttls(self, *, server_hostname):
        self.starttls_hostname = server_hostname

    async def login(self, username, password):
        self.login_args = (username, password)

    async def send_message(self, message):
        if self.fail_send:
            raise RuntimeError("smtp unavailable")
        self.sent_message = message


@pytest.mark.asyncio
async def test_send_email_rejects_private_smtp_host_before_network(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("aiosmtplib.send must not be called")

    monkeypatch.setattr("services.email_client.aiosmtplib.send", fail_if_called)

    with pytest.raises(ValueError, match="SMTP server is not allowed"):
        message_params = email_client.EmailMessageParams(
            to_address="test@example.com",
            subject="Test",
            body="Body",
        )
        smtp_config = email_client.SmtpConfig(
            smtp_server="127.0.0.1",
            smtp_port=587,
            smtp_username="testuser",
        )
        await email_client.send_email(
            message_params=message_params,
            smtp_config=smtp_config,
        )


@pytest.mark.asyncio
async def test_send_email_uses_validated_address_without_second_dns(monkeypatch):
    async def fail_legacy_send(*args, **kwargs):
        raise AssertionError("aiosmtplib.send must not resolve the hostname again")

    smtp_socket = _make_socket()
    smtp_destination = email_client.ValidatedSmtpDestination(
        hostname="smtp.example.com",
        port=587,
        family=socket.AF_INET,
        socktype=socket.SOCK_STREAM,
        proto=6,
        sockaddr=("8.8.8.8", 587),
    )

    async def fake_pinned_send(message, **kwargs):
        assert kwargs["smtp_socket"] is smtp_socket
        assert kwargs["smtp_server"] == "smtp.example.com"
        assert kwargs["smtp_port"] == 587
        return {"status": "sent", "simulated": False}

    async def fake_connect_validated_socket(destination):
        assert destination is smtp_destination
        return smtp_socket

    monkeypatch.setattr("services.email_client.aiosmtplib.send", fail_legacy_send)
    monkeypatch.setattr(
        "services.email_client._send_pinned_smtp_message",
        fake_pinned_send,
        raising=False,
    )
    monkeypatch.setattr(
        "services.email_client._connect_validated_smtp_socket",
        fake_connect_validated_socket,
        raising=False,
    )

    validate_calls = []

    def fake_validate_smtp_destination(smtp_server, smtp_port, *, resolve_host=True):
        validate_calls.append(resolve_host)
        assert smtp_server == "smtp.example.com"
        assert smtp_port == 587
        return smtp_destination

    monkeypatch.setattr(
        "services.email_client.validate_smtp_destination",
        fake_validate_smtp_destination,
    )

    message_params = email_client.EmailMessageParams(
        to_address="test@example.com",
        subject="Test",
        body="Body",
    )
    smtp_config = email_client.SmtpConfig(
        smtp_server="smtp.example.com",
        smtp_port=587,
        smtp_username="testuser",
    )
    result = await email_client.send_email(
        message_params=message_params,
        smtp_config=smtp_config,
    )

    assert result == {"status": "sent", "simulated": False}
    assert validate_calls == [True]
    assert smtp_socket.fileno() == -1


@pytest.mark.asyncio
async def test_connect_validated_socket_uses_pre_resolved_address_without_dns(
    monkeypatch,
):
    monkeypatch.setattr(email_client.settings, "ALLOWED_SMTP_HOSTS", "smtp.example.com")
    monkeypatch.setattr(email_client.settings, "ALLOWED_SMTP_PORTS", "587")
    getaddrinfo_calls = []

    def fake_getaddrinfo(*args, **kwargs):
        getaddrinfo_calls.append((args, kwargs))
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 587))]

    monkeypatch.setattr(email_client.socket, "getaddrinfo", fake_getaddrinfo)

    destination = email_client.validate_smtp_destination("smtp.example.com", 587)

    def fail_getaddrinfo(*args, **kwargs):
        raise AssertionError("connection must use the pre-resolved SMTP address")

    monkeypatch.setattr(email_client.socket, "getaddrinfo", fail_getaddrinfo)
    connected_sockaddrs = []
    loop = asyncio.get_running_loop()

    async def fake_sock_connect(sock, sockaddr):
        connected_sockaddrs.append(sockaddr)

    monkeypatch.setattr(loop, "sock_connect", fake_sock_connect)

    smtp_socket = await email_client._connect_validated_smtp_socket(destination)
    try:
        assert connected_sockaddrs == [("8.8.8.8", 587)]
    finally:
        smtp_socket.close()
    assert len(getaddrinfo_calls) == 1


@pytest.mark.asyncio
async def test_connect_validated_socket_rejects_unresolved_hostname_sockaddr(
    monkeypatch,
):
    destination = email_client.ValidatedSmtpDestination(
        hostname="smtp.example.com",
        port=587,
        family=socket.AF_INET,
        socktype=socket.SOCK_STREAM,
        proto=6,
        sockaddr=("smtp.example.com", 587),
    )

    async def fail_sock_connect(*args, **kwargs):
        raise AssertionError("hostname sockaddrs must fail before network egress")

    monkeypatch.setattr(asyncio.get_running_loop(), "sock_connect", fail_sock_connect)

    with pytest.raises(ValueError, match=email_client.SMTP_HOST_NOT_ALLOWED):
        await email_client._connect_validated_smtp_socket(destination)


@pytest.mark.asyncio
async def test_send_email_pins_first_validated_sockaddr_across_dns_rebinding(
    monkeypatch,
):
    monkeypatch.setattr(email_client.settings, "ALLOWED_SMTP_HOSTS", "smtp.example.com")
    monkeypatch.setattr(email_client.settings, "ALLOWED_SMTP_PORTS", "587")
    getaddrinfo_calls = []

    def fake_getaddrinfo(*args, **kwargs):
        getaddrinfo_calls.append((args, kwargs))
        if len(getaddrinfo_calls) == 1:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 587))]
        raise AssertionError("send_email must not perform a second DNS lookup")

    monkeypatch.setattr(email_client.socket, "getaddrinfo", fake_getaddrinfo)
    connected_sockaddrs = []

    async def fake_sock_connect(sock, sockaddr):
        connected_sockaddrs.append(sockaddr)

    monkeypatch.setattr(asyncio.get_running_loop(), "sock_connect", fake_sock_connect)

    async def fake_pinned_send(message, **kwargs):
        assert kwargs["smtp_server"] == "smtp.example.com"
        assert kwargs["smtp_socket"].fileno() != -1
        return {"status": "sent", "simulated": False}

    monkeypatch.setattr(email_client, "_send_pinned_smtp_message", fake_pinned_send)

    message_params = email_client.EmailMessageParams(
        to_address="test@example.com",
        subject="Test",
        body="Body",
    )
    smtp_config = email_client.SmtpConfig(
        smtp_server="smtp.example.com",
        smtp_port=587,
        smtp_username="testuser",
    )
    result = await email_client.send_email(
        message_params=message_params,
        smtp_config=smtp_config,
    )

    assert result == {"status": "sent", "simulated": False}
    assert len(getaddrinfo_calls) == 1
    assert connected_sockaddrs == [("8.8.8.8", 587)]


def test_smtp_destination_rejects_rebound_private_answer_on_fresh_validation(
    monkeypatch,
):
    monkeypatch.setattr(email_client.settings, "ALLOWED_SMTP_HOSTS", "smtp.example.com")
    monkeypatch.setattr(email_client.settings, "ALLOWED_SMTP_PORTS", "587")
    answers = [
        [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 587))],
        [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 587))],
    ]

    def fake_getaddrinfo(*args, **kwargs):
        return answers.pop(0)

    monkeypatch.setattr(email_client.socket, "getaddrinfo", fake_getaddrinfo)

    destination = email_client.validate_smtp_destination("smtp.example.com", 587)
    assert destination.sockaddr == ("8.8.8.8", 587)

    with pytest.raises(ValueError, match=email_client.SMTP_HOST_NOT_ALLOWED):
        email_client.validate_smtp_destination("smtp.example.com", 587)


def test_pinned_starttls_uses_existing_transport_helper():
    source = inspect.getsource(email_client._send_pinned_smtp_message)

    assert ".starttls(" not in source
    assert "_starttls_existing_transport" in source


def test_implicit_tls_connection_uses_running_loop_instead_of_stale_client_loop():
    source = inspect.getsource(email_client._PinnedImplicitTlsSMTP._create_connection)

    assert "asyncio.get_running_loop()" in source
    assert "self.loop" not in source


def test_starttls_existing_transport_uses_public_aiosmtplib_api():
    source = inspect.getsource(email_client._starttls_existing_transport)

    assert "client.starttls" in source
    assert "._ehlo_or_helo_if_needed" not in source
    assert "._get_tls_context" not in source
    assert "._reset_server_state" not in source


@pytest.mark.asyncio
async def test_starttls_existing_transport_delegates_to_public_starttls_api():
    class PublicStarttlsClient:
        def __init__(self):
            self.calls = []

        async def starttls(self, *, server_hostname, timeout):
            self.calls.append((server_hostname, timeout))

    client = PublicStarttlsClient()

    await email_client._starttls_existing_transport(
        client,  # type: ignore[arg-type]
        tls_sni_hostname="smtp.example.com",
    )

    assert client.calls == [("smtp.example.com", email_client.SMTP_TIMEOUT_SECONDS)]


@pytest.mark.asyncio
async def test_pinned_smtp_send_passes_original_hostname_and_socket(monkeypatch):
    smtp_socket = _make_socket()
    fake_client = FakeSmtpClient()
    message_params = email_client.EmailMessageParams(
        to_address="test@example.com",
        subject="Test",
        body="Body",
    )
    message = email_client.build_email_message(
        message_params=message_params,
        from_address="sender@example.com",
    )

    def fake_build_client(**kwargs):
        assert kwargs == {
            "smtp_socket": smtp_socket,
            "smtp_server": "smtp.example.com",
            "smtp_port": 587,
        }
        return fake_client

    starttls_hostnames = []

    async def fake_starttls_existing_transport(client, *, tls_sni_hostname):
        assert client is fake_client
        starttls_hostnames.append(tls_sni_hostname)

    monkeypatch.setattr("services.email_client._build_smtp_client", fake_build_client)
    monkeypatch.setattr(
        "services.email_client._starttls_existing_transport",
        fake_starttls_existing_transport,
    )

    result = await email_client._send_pinned_smtp_message(
        message,
        smtp_socket=smtp_socket,
        smtp_server="smtp.example.com",
        smtp_port=587,
        smtp_username="testuser",
        smtp_password=TEST_SMTP_PASSWORD,
    )

    assert result == {"status": "sent", "simulated": False}
    assert fake_client.entered is True
    assert fake_client.exited is True
    assert starttls_hostnames == ["smtp.example.com"]
    assert fake_client.login_args == ("testuser", TEST_SMTP_PASSWORD)
    assert fake_client.sent_message is message
    assert smtp_socket.fileno() == -1


def test_implicit_tls_smtp_client_keeps_original_tls_hostname():
    smtp_socket = _make_socket()
    try:
        client = email_client._build_smtp_client(
            smtp_socket=smtp_socket,
            smtp_server="smtp.example.com",
            smtp_port=465,
        )

        assert client.sock is smtp_socket
        assert client.use_tls is True
        assert client.hostname == "smtp.example.com"
        assert getattr(client, "_tls_server_hostname") == "smtp.example.com"
    finally:
        smtp_socket.close()


@pytest.mark.asyncio
async def test_send_email_raises_error_when_smtp_fails(monkeypatch):
    fake_client = FakeSmtpClient(fail_send=True)
    smtp_socket = _make_socket()
    smtp_destination = email_client.ValidatedSmtpDestination(
        hostname="smtp.example.com",
        port=587,
        family=socket.AF_INET,
        socktype=socket.SOCK_STREAM,
        proto=6,
        sockaddr=("8.8.8.8", 587),
    )

    async def fake_connect_validated_socket(destination):
        assert destination is smtp_destination
        return smtp_socket

    def fake_build_client(**kwargs):
        return fake_client

    monkeypatch.setattr(
        "services.email_client._connect_validated_smtp_socket",
        fake_connect_validated_socket,
    )
    monkeypatch.setattr("services.email_client._build_smtp_client", fake_build_client)

    def fake_validate_smtp_destination(smtp_server, smtp_port, *, resolve_host=True):
        assert resolve_host is True
        assert smtp_server == "smtp.example.com"
        assert smtp_port == 587
        return smtp_destination

    monkeypatch.setattr(
        "services.email_client.validate_smtp_destination",
        fake_validate_smtp_destination,
    )

    with pytest.raises(Exception, match="Failed to send email"):
        message_params = email_client.EmailMessageParams(
            to_address="test@example.com",
            subject="Test Failure",
            body="Should fail because SMTP server is invalid",
        )
        smtp_config = email_client.SmtpConfig(
            smtp_server="smtp.example.com",
            smtp_port=587,
            smtp_username="testuser",
        )
        await email_client.send_email(
            message_params=message_params,
            smtp_config=smtp_config,
        )
    assert smtp_socket.fileno() == -1
