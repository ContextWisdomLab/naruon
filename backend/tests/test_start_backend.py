from __future__ import annotations

import secrets
import socket

from scripts import start_backend


def _clear_runtime_settings(monkeypatch) -> None:
    for setting_name in (
        "DATABASE_URL",
        "AUTH_SESSION_HMAC_SECRET",
        "OIDC_ISSUER_URL",
        "OIDC_CLIENT_ID",
        "OIDC_JWKS_URL",
        "ALLOWED_OIDC_HOSTS",
        "NARUON_ENV_FILE",
    ):
        monkeypatch.delenv(setting_name, raising=False)
    monkeypatch.setenv("NARUON_ENV_FILE", "/dev/null")


def _patch_oidc_dns(monkeypatch, address: str | dict[str, list[str]]) -> None:
    addresses_by_host = (
        {"login.example.test": [address]} if isinstance(address, str) else address
    )

    def fake_getaddrinfo(host: str, port: int, *args, **kwargs):
        addresses = addresses_by_host.get(host)
        if addresses is None:
            raise socket.gaierror(f"test DNS blocked for {host}")
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved_address, port))
            for resolved_address in addresses
        ]

    monkeypatch.setattr("core.url_validation.socket.getaddrinfo", fake_getaddrinfo)


def test_start_backend_reports_missing_database_url_without_import_traceback(
    monkeypatch, tmp_path, capsys
):
    _clear_runtime_settings(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)

    exit_code = start_backend.main([])
    captured = capsys.readouterr()

    assert exit_code == 78
    assert "Missing required runtime settings: DATABASE_URL" in captured.err
    assert "AUTH_SESSION_HMAC_SECRET" in captured.err
    assert "Traceback" not in captured.err
    assert "pydantic" not in captured.err


def test_start_backend_accepts_operator_home_env_file(monkeypatch, tmp_path):
    _clear_runtime_settings(monkeypatch)
    monkeypatch.delenv("NARUON_ENV_FILE")
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    (home_dir / ".env").write_text(
        "\n".join(
            [
                "DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test_db",
                f"AUTH_SESSION_HMAC_SECRET={secrets.token_urlsafe(48)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.chdir(tmp_path)

    assert start_backend.validate_runtime_settings() == []


def test_start_backend_respects_explicit_empty_bootstrap_transport(
    monkeypatch, tmp_path
):
    """Preflight must use the same selected source as Settings and CI."""
    _clear_runtime_settings(monkeypatch)
    monkeypatch.chdir(tmp_path)
    # The RED probe must never read real operator files or dump environment values.
    monkeypatch.setattr(
        start_backend,
        "_read_env_file",
        lambda file_path: (
            {"DATABASE_URL": "unit-probe"} if str(file_path) == ".env" else {}
        ),
    )
    monkeypatch.setenv("NARUON_ENV_FILE", "/dev/null")
    runtime_values, checked_paths = start_backend._runtime_values()
    assert "DATABASE_URL" not in tuple(runtime_values)
    assert [str(checked_path) for checked_path in checked_paths] == ["/dev/null"]


def test_start_backend_can_run_preflight_only_with_valid_settings(monkeypatch):
    _clear_runtime_settings(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("NARUON_STARTUP_PREFLIGHT_ONLY", "1")

    assert start_backend.main([]) == 0


def test_start_backend_rejects_partial_oidc_configuration(monkeypatch, tmp_path):
    _clear_runtime_settings(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://login.example.test/realms/naruon")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)

    assert start_backend.validate_runtime_settings() == [
        "OIDC_ISSUER_URL, OIDC_CLIENT_ID, and OIDC_JWKS_URL must be set together"
    ]


def test_start_backend_rejects_oidc_without_allowed_hosts(monkeypatch, tmp_path):
    _clear_runtime_settings(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://login.example.test/realms/naruon")
    monkeypatch.setenv("OIDC_CLIENT_ID", "naruon-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://login.example.test/realms/naruon/jwks")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)

    assert start_backend.validate_runtime_settings() == [
        "ALLOWED_OIDC_HOSTS must list trusted OIDC issuer and JWKS hosts"
    ]


def test_start_backend_rejects_untrusted_oidc_jwks_host(monkeypatch, tmp_path):
    _clear_runtime_settings(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://login.example.test/realms/naruon")
    monkeypatch.setenv("OIDC_CLIENT_ID", "naruon-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://127.0.0.1/jwks")
    monkeypatch.setenv("ALLOWED_OIDC_HOSTS", "login.example.test")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    _patch_oidc_dns(monkeypatch, "93.184.216.34")

    assert start_backend.validate_runtime_settings() == [
        "OIDC_JWKS_URL host must be listed in ALLOWED_OIDC_HOSTS"
    ]


def test_start_backend_rejects_oidc_jwks_host_outside_issuer_domain(
    monkeypatch, tmp_path
):
    _clear_runtime_settings(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://login.example.test/realms/naruon")
    monkeypatch.setenv("OIDC_CLIENT_ID", "naruon-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://jwks.example.test/realms/naruon/jwks")
    monkeypatch.setenv("ALLOWED_OIDC_HOSTS", "login.example.test,jwks.example.test")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    _patch_oidc_dns(
        monkeypatch,
        {
            "login.example.test": ["93.184.216.34"],
            "jwks.example.test": ["93.184.216.34"],
        },
    )

    assert start_backend.validate_runtime_settings() == [
        "OIDC_JWKS_URL host must match or be a subdomain of OIDC_ISSUER_URL host"
    ]


def test_start_backend_rejects_oidc_hostname_resolving_private_address(
    monkeypatch, tmp_path
):
    _clear_runtime_settings(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://login.example.test/realms/naruon")
    monkeypatch.setenv("OIDC_CLIENT_ID", "naruon-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://login.example.test/realms/naruon/jwks")
    monkeypatch.setenv("ALLOWED_OIDC_HOSTS", "login.example.test")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    _patch_oidc_dns(monkeypatch, "192.168.1.1")

    assert start_backend.validate_runtime_settings() == [
        "OIDC_ISSUER_URL resolved IP host must be globally routable",
        "OIDC_JWKS_URL resolved IP host must be globally routable",
    ]
