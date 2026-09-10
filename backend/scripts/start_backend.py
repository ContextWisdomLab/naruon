from __future__ import annotations

import os
import sys
from argparse import ArgumentParser
from collections.abc import Sequence
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.env_paths import operator_env_file_paths  # noqa: E402
from core.runtime_secrets import validate_auth_session_hmac_secret_value  # noqa: E402
from core.url_validation import (  # noqa: E402
    parse_allowed_hosts,
    validate_https_url_host_details,
    validate_same_or_subdomain_host,
)

DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 8000
REQUIRED_SETTINGS = ("DATABASE_URL", "AUTH_SESSION_HMAC_SECRET")
OIDC_SETTINGS = ("OIDC_ISSUER_URL", "OIDC_CLIENT_ID", "OIDC_JWKS_URL")


def _strip_env_value(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists() or not path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        if key:
            values[key] = _strip_env_value(value)
    return values


def _runtime_values() -> tuple[dict[str, str], list[Path]]:
    values: dict[str, str] = {}
    checked_paths: list[Path] = []
    for env_file in operator_env_file_paths():
        path = Path(env_file)
        checked_paths.append(path)
        values.update(_read_env_file(path))
    values.update({key: value for key, value in os.environ.items() if value})
    return values, checked_paths


def validate_runtime_settings() -> list[str]:
    values, checked_paths = _runtime_values()
    messages: list[str] = []

    missing_settings = [
        setting_name for setting_name in REQUIRED_SETTINGS if not values.get(setting_name)
    ]
    if missing_settings:
        checked = ", ".join(str(path) for path in checked_paths)
        messages.append(
            "Missing required runtime settings: "
            f"{', '.join(missing_settings)}. "
            "Set them in the container environment, Docker Compose env file, "
            f"or one of: {checked}."
        )

    session_secret = values.get("AUTH_SESSION_HMAC_SECRET")
    if session_secret:
        try:
            validate_auth_session_hmac_secret_value(session_secret)
        except ValueError as exc:
            messages.append(str(exc))

    configured_oidc = [
        setting_name for setting_name in OIDC_SETTINGS if values.get(setting_name)
    ]
    if configured_oidc and len(configured_oidc) != len(OIDC_SETTINGS):
        messages.append(
            "OIDC_ISSUER_URL, OIDC_CLIENT_ID, and OIDC_JWKS_URL must be set together"
        )
    if len(configured_oidc) == len(OIDC_SETTINGS):
        allowed_oidc_hosts = parse_allowed_hosts(values.get("ALLOWED_OIDC_HOSTS", ""))
        if not allowed_oidc_hosts:
            messages.append(
                "ALLOWED_OIDC_HOSTS must list trusted OIDC issuer and JWKS hosts"
            )
        else:
            issuer_url = None
            jwks_url = None
            try:
                issuer_url = validate_https_url_host_details(
                    "OIDC_ISSUER_URL",
                    values["OIDC_ISSUER_URL"],
                    allowed_oidc_hosts,
                    "ALLOWED_OIDC_HOSTS",
                )
            except ValueError as exc:
                messages.append(str(exc))
            try:
                jwks_url = validate_https_url_host_details(
                    "OIDC_JWKS_URL",
                    values["OIDC_JWKS_URL"],
                    allowed_oidc_hosts,
                    "ALLOWED_OIDC_HOSTS",
                )
            except ValueError as exc:
                messages.append(str(exc))
            if issuer_url is not None and jwks_url is not None:
                try:
                    validate_same_or_subdomain_host(
                        "OIDC_JWKS_URL",
                        jwks_url.hostname,
                        "OIDC_ISSUER_URL",
                        issuer_url.hostname,
                    )
                except ValueError as exc:
                    messages.append(str(exc))

    return messages


def _argument_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Validate runtime settings and start Naruon")
    parser.add_argument("--host", default=DEFAULT_SERVER_HOST)
    parser.add_argument("--port", default=DEFAULT_SERVER_PORT, type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    errors = validate_runtime_settings()
    if errors:
        print("Startup configuration error:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 78

    if os.environ.get("NARUON_STARTUP_PREFLIGHT_ONLY") == "1":
        return 0

    import uvicorn

    uvicorn.run("main:app", host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
