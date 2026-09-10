import os
import secrets
import socket
from typing import Any, cast

import pytest
from pydantic import ValidationError

TEST_AUTH_SESSION_HMAC_SECRET = os.environ.setdefault(
    "AUTH_SESSION_HMAC_SECRET", secrets.token_urlsafe(48)
)

# Set required environment variables before importing settings
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/test_db"

from core.config import Settings, parse_allowed_cors_origins, settings  # noqa: E402


def _settings_without_env_file() -> Settings:
    return Settings(**cast(dict[str, Any], {"_env_file": None}))


def _set_required_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", TEST_AUTH_SESSION_HMAC_SECRET)


def _patch_oidc_dns(
    monkeypatch: pytest.MonkeyPatch,
    host_addresses: dict[str, list[str]] | None = None,
) -> None:
    addresses_by_host = host_addresses or {"login.example.com": ["93.184.216.34"]}

    def fake_getaddrinfo(host: str, port: int, *args, **kwargs):
        addresses = addresses_by_host.get(host)
        if addresses is None:
            raise socket.gaierror(f"test DNS blocked for {host}")
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))
            for address in addresses
        ]

    monkeypatch.setattr("core.url_validation.socket.getaddrinfo", fake_getaddrinfo)


def test_global_config():
    assert hasattr(settings, "DATABASE_URL")
    assert hasattr(settings, "DEBUG")
    assert hasattr(settings, "RUNTIME_ENVIRONMENT")
    assert hasattr(settings, "ENCRYPTION_KEY")


def test_production_settings_do_not_expose_dev_header_bypass_controls():
    assert "TRUST_DEV_HEADERS" not in settings.__class__.model_fields
    assert "DEV_AUTH_TOKEN" not in settings.__class__.model_fields


def test_database_url_is_required(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        _settings_without_env_file()


def test_database_url_loads_from_environment(monkeypatch):
    database_url = "postgresql+asyncpg://test:test@localhost:5432/test_db"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", TEST_AUTH_SESSION_HMAC_SECRET)

    loaded_settings = _settings_without_env_file()

    assert loaded_settings.DATABASE_URL == database_url


def test_readonly_database_url_is_optional_and_loads_from_environment(monkeypatch):
    _set_required_runtime_env(monkeypatch)

    without_replica = _settings_without_env_file()

    assert without_replica.READONLY_DATABASE_URL is None

    replica_url = "postgresql+asyncpg://readonly:readonly@localhost:5433/test_db"
    monkeypatch.setenv("READONLY_DATABASE_URL", replica_url)

    with_replica = _settings_without_env_file()

    assert with_replica.READONLY_DATABASE_URL == replica_url

    monkeypatch.setenv("READONLY_DATABASE_URL", "")

    blank_replica = _settings_without_env_file()

    assert blank_replica.READONLY_DATABASE_URL is None


def test_allowed_cors_origins_are_validated_and_normalized(monkeypatch):
    _set_required_runtime_env(monkeypatch)
    monkeypatch.setenv(
        "ALLOWED_CORS_ORIGINS",
        " https://Example.com:443 , http://localhost:3000 , http://Example.com:80 , https://example.com:8443 ",
    )

    loaded_settings = _settings_without_env_file()

    assert loaded_settings.ALLOWED_CORS_ORIGINS_LIST == [
        "https://example.com",
        "http://localhost:3000",
        "http://example.com",
        "https://example.com:8443",
    ]


def test_parse_allowed_cors_origins_normalizes_entries_and_ignores_empty_items():
    origins = parse_allowed_cors_origins(
        " https://Example.com:443 , http://localhost:3000 ,  ,, https://test.net "
    )

    assert origins == [
        "https://example.com",
        "http://localhost:3000",
        "https://test.net",
    ]


@pytest.mark.parametrize(
    ("allowed_origins", "error_match"),
    [
        ("*", "must not include wildcards"),
        ("https://*.example.com", "must not include wildcards"),
        ("ws://example.com", "entries must use http or https"),
        ("ftp://example.com", "entries must use http or https"),
        ("https://user:pass@example.com", "entries must not include userinfo"),
        ("https://", "entries must include a host"),
        (
            "https://example.com/path",
            "entries must be origins without path, query, or fragment",
        ),
        (
            "https://example.com?query=1",
            "entries must be origins without path, query, or fragment",
        ),
        (
            "https://example.com#fragment",
            "entries must be origins without path, query, or fragment",
        ),
        ("https://example.com:invalid_port", "entries must include a valid port"),
    ],
)
def test_parse_allowed_cors_origins_rejects_unsafe_entries(
    allowed_origins: str, error_match: str
):
    with pytest.raises(ValueError, match=error_match):
        parse_allowed_cors_origins(allowed_origins)


@pytest.mark.parametrize(
    "allowed_origins",
    [
        "*",
        "https://*.example.com",
        "ftp://example.com",
        "https://example.com/path",
        "https://example.com?debug=1",
        "https://user@example.com",
    ],
)
def test_allowed_cors_origins_reject_unsafe_values(monkeypatch, allowed_origins):
    _set_required_runtime_env(monkeypatch)
    monkeypatch.setenv("ALLOWED_CORS_ORIGINS", allowed_origins)

    with pytest.raises(ValidationError, match="ALLOWED_CORS_ORIGINS"):
        _settings_without_env_file()


def test_settings_load_repo_root_env_when_started_from_backend_directory(
    monkeypatch, tmp_path
):
    monkeypatch.delenv("NARUON_ENV_FILE", raising=False)
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    repo_env = tmp_path / ".env"
    database_url = "postgresql+asyncpg://root:root@localhost:5432/root_db"
    repo_env.write_text(
        "\n".join(
            [
                f"DATABASE_URL={database_url}",
                f"AUTH_SESSION_HMAC_SECRET={TEST_AUTH_SESSION_HMAC_SECRET}",
            ]
        )
        + "\n"
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AUTH_SESSION_HMAC_SECRET", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "unit_home"))
    monkeypatch.chdir(backend_dir)

    loaded_settings = Settings()

    assert loaded_settings.DATABASE_URL == database_url


def test_settings_load_operator_home_env_when_project_env_is_absent(
    monkeypatch, tmp_path
):
    monkeypatch.delenv("NARUON_ENV_FILE", raising=False)
    project_dir = tmp_path / "project" / "backend"
    home_dir = tmp_path / "home"
    project_dir.mkdir(parents=True)
    home_dir.mkdir()
    database_url = "postgresql+asyncpg://home:home@localhost:5432/home_db"
    (home_dir / ".env").write_text(
        "\n".join(
            [
                f"DATABASE_URL={database_url}",
                f"AUTH_SESSION_HMAC_SECRET={TEST_AUTH_SESSION_HMAC_SECRET}",
            ]
        )
        + "\n"
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AUTH_SESSION_HMAC_SECRET", raising=False)
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.chdir(project_dir)

    loaded_settings = Settings()

    assert loaded_settings.DATABASE_URL == database_url


def test_production_settings_reject_missing_auth_session_hmac_secret(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("RUNTIME_ENVIRONMENT", "production")
    monkeypatch.delenv("AUTH_SESSION_HMAC_SECRET", raising=False)

    with pytest.raises(ValidationError, match="AUTH_SESSION_HMAC_SECRET is required"):
        _settings_without_env_file()


def test_production_settings_reject_short_auth_session_hmac_secret(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("RUNTIME_ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", "weak-secret")

    with pytest.raises(ValidationError, match="at least 32 bytes"):
        _settings_without_env_file()


def test_production_settings_reject_repeated_auth_session_hmac_secret(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("RUNTIME_ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", "A" * 32)

    with pytest.raises(ValidationError, match="must not be a repeated character"):
        _settings_without_env_file()


@pytest.mark.parametrize(
    "auth_session_hmac_secret",
    [
        "abcd" * 8,
        "abcdefgh" * 4,
        "qwertyuiop" * 4,
    ],
)
def test_production_settings_reject_low_entropy_auth_session_hmac_secret(
    monkeypatch, auth_session_hmac_secret
):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp/test.db")
    monkeypatch.setenv("RUNTIME_ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", auth_session_hmac_secret)

    with pytest.raises(ValidationError, match="must have higher entropy"):
        _settings_without_env_file()


def test_settings_reject_public_auth_session_hmac_fixture(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("RUNTIME_ENVIRONMENT", "production")
    monkeypatch.setenv(
        "AUTH_SESSION_HMAC_SECRET",
        "naruon-session-hmac-token-32-byte-minimum",
    )

    with pytest.raises(ValidationError, match="public fixture value"):
        _settings_without_env_file()


def test_non_production_settings_reject_missing_auth_session_hmac_secret(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("RUNTIME_ENVIRONMENT", "local")
    monkeypatch.delenv("AUTH_SESSION_HMAC_SECRET", raising=False)

    with pytest.raises(ValidationError, match="AUTH_SESSION_HMAC_SECRET is required"):
        _settings_without_env_file()


def test_non_production_settings_reject_short_auth_session_hmac_secret(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("RUNTIME_ENVIRONMENT", "local")
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", "weak-secret")

    with pytest.raises(ValidationError, match="at least 32 bytes"):
        _settings_without_env_file()


def test_settings_repr_redacts_auth_session_hmac_secret(monkeypatch):
    secret = TEST_AUTH_SESSION_HMAC_SECRET
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", secret)

    loaded_settings = _settings_without_env_file()

    assert secret not in repr(loaded_settings)
    assert "**********" in repr(loaded_settings)


def test_openai_config():
    from core.config import settings

    assert hasattr(settings, "OPENAI_BASE_URL")
    assert hasattr(settings, "OPENAI_EMBEDDING_MODEL")
    assert hasattr(settings, "OPENAI_MODEL")


def test_oidc_settings_must_be_configured_together(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", TEST_AUTH_SESSION_HMAC_SECRET)
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://login.example.com/realms/naruon")
    monkeypatch.delenv("OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv("OIDC_JWKS_URL", raising=False)

    with pytest.raises(
        ValidationError,
        match="OIDC_ISSUER_URL, OIDC_CLIENT_ID, and OIDC_JWKS_URL",
    ):
        _settings_without_env_file()


def test_oidc_settings_accept_complete_configuration(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", TEST_AUTH_SESSION_HMAC_SECRET)
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://login.example.com/realms/naruon")
    monkeypatch.setenv("OIDC_CLIENT_ID", "naruon-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://login.example.com/realms/naruon/jwks")
    monkeypatch.setenv("ALLOWED_OIDC_HOSTS", "login.example.com")
    _patch_oidc_dns(monkeypatch)

    loaded_settings = _settings_without_env_file()

    assert loaded_settings.OIDC_CLIENT_ID == "naruon-api"


def test_oidc_settings_reject_jwks_host_outside_issuer_domain(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", TEST_AUTH_SESSION_HMAC_SECRET)
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://login.example.com/realms/naruon")
    monkeypatch.setenv("OIDC_CLIENT_ID", "naruon-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://jwks.example.com/realms/naruon/jwks")
    monkeypatch.setenv("ALLOWED_OIDC_HOSTS", "login.example.com,jwks.example.com")
    _patch_oidc_dns(
        monkeypatch,
        {
            "login.example.com": ["93.184.216.34"],
            "jwks.example.com": ["93.184.216.34"],
        },
    )

    with pytest.raises(
        ValidationError,
        match="OIDC_JWKS_URL host must match or be a subdomain of OIDC_ISSUER_URL host",
    ):
        _settings_without_env_file()


def test_oidc_settings_reject_hostname_resolving_private_address(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", TEST_AUTH_SESSION_HMAC_SECRET)
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://login.example.com/realms/naruon")
    monkeypatch.setenv("OIDC_CLIENT_ID", "naruon-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://login.example.com/realms/naruon/jwks")
    monkeypatch.setenv("ALLOWED_OIDC_HOSTS", "login.example.com")
    _patch_oidc_dns(monkeypatch, {"login.example.com": ["192.168.1.1"]})

    with pytest.raises(
        ValidationError,
        match="OIDC_ISSUER_URL resolved IP host must be globally routable",
    ):
        _settings_without_env_file()


def test_oidc_settings_reject_hostname_resolving_mixed_private_address(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", TEST_AUTH_SESSION_HMAC_SECRET)
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://login.example.com/realms/naruon")
    monkeypatch.setenv("OIDC_CLIENT_ID", "naruon-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://login.example.com/realms/naruon/jwks")
    monkeypatch.setenv("ALLOWED_OIDC_HOSTS", "login.example.com")
    _patch_oidc_dns(
        monkeypatch,
        {"login.example.com": ["93.184.216.34", "192.168.1.1"]},
    )

    with pytest.raises(
        ValidationError,
        match="OIDC_ISSUER_URL resolved IP host must be globally routable",
    ):
        _settings_without_env_file()


def test_oidc_settings_reject_missing_allowed_hosts(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", TEST_AUTH_SESSION_HMAC_SECRET)
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://login.example.com/realms/naruon")
    monkeypatch.setenv("OIDC_CLIENT_ID", "naruon-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://login.example.com/realms/naruon/jwks")
    monkeypatch.delenv("ALLOWED_OIDC_HOSTS", raising=False)

    with pytest.raises(
        ValidationError,
        match="ALLOWED_OIDC_HOSTS must list trusted OIDC issuer and JWKS hosts",
    ):
        _settings_without_env_file()


def test_oidc_settings_reject_untrusted_jwks_host(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", TEST_AUTH_SESSION_HMAC_SECRET)
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://login.example.com/realms/naruon")
    monkeypatch.setenv("OIDC_CLIENT_ID", "naruon-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://metadata.google.internal/jwks")
    monkeypatch.setenv("ALLOWED_OIDC_HOSTS", "login.example.com")
    _patch_oidc_dns(monkeypatch)

    with pytest.raises(
        ValidationError,
        match="OIDC_JWKS_URL host must be listed in ALLOWED_OIDC_HOSTS",
    ):
        _settings_without_env_file()


def test_oidc_settings_reject_non_https_issuer(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", TEST_AUTH_SESSION_HMAC_SECRET)
    monkeypatch.setenv("OIDC_ISSUER_URL", "http://login.example.com/realms/naruon")
    monkeypatch.setenv("OIDC_CLIENT_ID", "naruon-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://login.example.com/realms/naruon/jwks")
    monkeypatch.setenv("ALLOWED_OIDC_HOSTS", "login.example.com")

    with pytest.raises(ValidationError, match="OIDC_ISSUER_URL must use https"):
        _settings_without_env_file()


def test_oidc_settings_reject_private_ip_literal_even_when_allowlisted(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    monkeypatch.setenv("AUTH_SESSION_HMAC_SECRET", TEST_AUTH_SESSION_HMAC_SECRET)
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://127.0.0.1/realms/naruon")
    monkeypatch.setenv("OIDC_CLIENT_ID", "naruon-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://127.0.0.1/jwks")
    monkeypatch.setenv("ALLOWED_OIDC_HOSTS", "127.0.0.1")

    with pytest.raises(
        ValidationError,
        match="OIDC_ISSUER_URL IP host must be globally routable",
    ):
        _settings_without_env_file()
