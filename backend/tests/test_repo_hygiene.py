from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dockerignore_excludes_nested_environment_files_but_keeps_examples():
    dockerignore = (REPO_ROOT / ".dockerignore").read_text()

    assert ".env*" in dockerignore
    assert "**/.env*" in dockerignore
    assert "!.env.example" in dockerignore
    assert "!**/.env.example" in dockerignore


def test_backend_dockerfile_suppresses_pip_root_warning():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()

    assert "PIP_ROOT_USER_ACTION=ignore" in dockerfile
    assert "PIP_DISABLE_PIP_VERSION_CHECK=1" in dockerfile


def test_backend_dockerfile_runtime_stages_run_as_non_root_user():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    backend_cmd = (
        'CMD ["python", "scripts/start_backend.py", "--host", "0.0.0.0", "--port", "8000"]'
    )
    combined_cmd = 'CMD ["/app/scripts/docker_entrypoint.sh"]'

    assert "useradd --system --create-home --home-dir /home/appuser" in dockerfile
    assert "chown -R appuser:appuser /app" in dockerfile
    assert dockerfile.find("USER appuser") < dockerfile.find(backend_cmd)
    assert dockerfile.rfind("USER appuser") < dockerfile.find(combined_cmd)
    assert "HEALTHCHECK --interval=30s --timeout=5s" in dockerfile
    assert "http://127.0.0.1:8000/" in dockerfile
    assert "http://127.0.0.1:3000/" in dockerfile


def test_frontend_dockerfile_runs_as_non_root_user():
    dockerfile = (REPO_ROOT / "frontend" / "Dockerfile").read_text()

    assert "RUN chown -R node:node /app" in dockerfile
    assert "USER node" in dockerfile
    assert dockerfile.rfind("USER node") > dockerfile.rfind("RUN pnpm run build")
    assert "HEALTHCHECK --interval=30s --timeout=5s" in dockerfile
    assert "fetch('http://127.0.0.1:' + (process.env.PORT || '3000'))" in dockerfile


def test_ollama_dockerfile_keeps_pulled_models_available_to_runtime_user():
    dockerfile = (REPO_ROOT / "Dockerfile.ollama").read_text()

    assert (
        "FROM ollama/ollama@sha256:"
        "b88c73ace3e115f8ec53dc8761ae1c0aabfa675406e3681786b98757ce050f42"
        in dockerfile
    )
    assert "FROM ollama/ollama:latest\n" not in dockerfile
    assert "ENV OLLAMA_MODELS=/usr/share/ollama/.ollama/models" in dockerfile
    assert "useradd --system --create-home --home-dir /home/ollama" in dockerfile
    assert "curl " not in dockerfile
    assert "for attempt in $(seq 1 60)" in dockerfile
    assert "if ollama list > /dev/null 2>&1" in dockerfile
    assert "cat /tmp/ollama-build.log; exit 1" in dockerfile
    assert "for pull_attempt in $(seq 1 5)" in dockerfile
    assert "upstream model registry unavailable" in dockerfile
    assert "retrying in ${sleep_seconds}s" in dockerfile
    assert 'model="gemma4:e2b-it-qat"' in dockerfile
    assert 'model="embeddinggemma"' in dockerfile
    assert 'ollama pull "${model}"' in dockerfile
    assert dockerfile.count("RUN set -eux;") >= 2
    assert dockerfile.find('model="gemma4:e2b-it-qat"') < dockerfile.find(
        'model="embeddinggemma"'
    )
    assert "ollama list | grep -E '^gemma4:e2b-it-qat[[:space:]]'" in dockerfile
    assert (
        "ollama list | grep -E '^embeddinggemma(:|[[:space:]])'" in dockerfile
    )
    assert "chown -R ollama:ollama /usr/share/ollama/.ollama" in dockerfile
    assert dockerfile.rfind("USER ollama") > dockerfile.rfind(
        "chown -R ollama:ollama /usr/share/ollama/.ollama"
    )
    assert "HEALTHCHECK --interval=30s --timeout=5s" in dockerfile
    assert "ollama list >/dev/null 2>&1 || exit 1" in dockerfile


def test_connector_dockerfile_has_non_http_healthcheck():
    dockerfile = (REPO_ROOT / "connector" / "Dockerfile").read_text()

    assert "USER connector" in dockerfile
    assert "HEALTHCHECK --interval=30s --timeout=5s" in dockerfile
    assert "from connector.main import DEFAULT_WS_URL" in dockerfile
    assert "DEFAULT_WS_URL.startswith('wss://')" in dockerfile


def test_backend_requirements_do_not_pin_yanked_email_validator():
    requirements = (REPO_ROOT / "backend" / "requirements.txt").read_text()

    assert "email-validator==2.1.0" not in requirements
    assert "email-validator==2.3.0" in requirements


def test_backend_requirements_pin_ruff_for_deterministic_ci():
    requirements = (REPO_ROOT / "backend" / "requirements.txt").read_text()

    assert "\nruff\n" not in f"\n{requirements}\n"
    assert "ruff==0.15.21" in requirements


def test_compose_gateway_services_disable_privilege_escalation():
    compose = (REPO_ROOT / "docker-compose.gateway.yml").read_text()
    traefik_block = compose.split("  traefik:", 1)[1].split("  keycloak:", 1)[0]

    assert "security_opt:" in traefik_block
    assert "- no-new-privileges:true" in traefik_block


def test_infra_compose_services_use_read_only_hardening_anchor():
    compose = (REPO_ROOT / "docker-compose.infra.yml").read_text()

    assert "x-service-hardening: &service-hardening" in compose
    assert "security_opt:" in compose
    assert "- no-new-privileges:true" in compose
    assert "read_only: true" in compose

    for service in (
        "traefik",
        "prometheus",
        "grafana",
        "loki",
        "tempo",
        "otel-collector",
        "keycloak",
    ):
        assert f"  {service}:\n    <<: *service-hardening" in compose

    assert "GF_SECURITY_ADMIN_PASSWORD=admin" not in compose
    assert (
        "GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:"
        "?GRAFANA_ADMIN_PASSWORD is not set}"
    ) in compose


def test_screenshot_utility_allows_only_local_static_routes():
    screenshot_script = (REPO_ROOT / "frontend" / "screenshot.cjs").read_text()

    assert "SCREENSHOT_ORIGIN = 'http://127.0.0.1:3000'" in screenshot_script
    assert "async function gotoScreenshotRoute(page, route)" in screenshot_script
    assert "switch (route)" in screenshot_script
    for route, url in {
        "/": "http://127.0.0.1:3000/",
        "/mail": "http://127.0.0.1:3000/mail",
        "/calendar": "http://127.0.0.1:3000/calendar",
        "/tasks": "http://127.0.0.1:3000/tasks",
        "/projects": "http://127.0.0.1:3000/projects",
        "/search": "http://127.0.0.1:3000/search",
        "/data": "http://127.0.0.1:3000/data",
        "/ai-hub": "http://127.0.0.1:3000/ai-hub",
        "/security": "http://127.0.0.1:3000/security",
        "/settings": "http://127.0.0.1:3000/settings",
    }.items():
        assert f"case '{route}':" in screenshot_script
        assert f"page.goto('{url}', GOTO_OPTIONS)" in screenshot_script
    assert "Unsupported screenshot route" in screenshot_script
    assert "nosemgrep" not in screenshot_script
    assert "console.error('Failed to capture route'" in screenshot_script
    assert "page.goto(url" not in screenshot_script
    assert "new URL(" not in screenshot_script
    assert "http://localhost:3000${route}" not in screenshot_script
    assert "console.error(`Failed to capture ${route}:`" not in screenshot_script


def test_compose_externalizes_postgres_credentials():
    compose = (REPO_ROOT / "docker-compose.yml").read_text()
    compose_without_runtime_preflights = (
        compose.replace(
            '$${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env before running Docker Compose}',
            "",
        )
        .replace(
            '$${AUTH_SESSION_HMAC_SECRET:?Set AUTH_SESSION_HMAC_SECRET in .env before running Docker Compose}',
            "",
        )
        .replace(
            '$${ENCRYPTION_KEY:?Set ENCRYPTION_KEY in .env before running Docker Compose}',
            "",
        )
    )

    assert "POSTGRES_PASSWORD: postgres" not in compose
    assert "postgres:postgres@" not in compose
    assert "POSTGRES_DB: ai_email" in compose
    assert "POSTGRES_USER: postgres" in compose
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}" in compose
    assert "- POSTGRES_PASSWORD" not in compose
    assert "POSTGRES_PASSWORD:-postgres" not in compose
    assert "${POSTGRES_PASSWORD" in compose
    assert "${POSTGRES_PASSWORD:?" not in compose_without_runtime_preflights
    assert '$${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env before running Docker Compose}' in compose
    assert "127.0.0.1:15432:5432" in compose
    assert "AUTH_SESSION_HMAC_SECRET" in compose
    assert "AUTH_SESSION_HMAC_SECRET: ${AUTH_SESSION_HMAC_SECRET}" in compose
    assert "- AUTH_SESSION_HMAC_SECRET" not in compose
    assert "${AUTH_SESSION_HMAC_SECRET:?" not in compose_without_runtime_preflights
    assert '$${AUTH_SESSION_HMAC_SECRET:?Set AUTH_SESSION_HMAC_SECRET in .env before running Docker Compose}' in compose
    assert "ENCRYPTION_KEY" in compose
    assert "ENCRYPTION_KEY: ${ENCRYPTION_KEY}" in compose
    assert "- ENCRYPTION_KEY" not in compose
    assert "${ENCRYPTION_KEY:?" not in compose_without_runtime_preflights
    assert '$${ENCRYPTION_KEY:?Set ENCRYPTION_KEY in .env before running Docker Compose}' in compose


def test_compose_allows_only_the_local_ollama_provider_host():
    local_compose = (REPO_ROOT / "docker-compose.yml").read_text()
    live_compose = (REPO_ROOT / "docker-compose.live-e2e.yml").read_text()

    def has_exact_compose_line(compose: str, *expected_lines: str) -> bool:
        normalized_lines = {
            line.strip().removeprefix("- ").strip() for line in compose.splitlines()
        }
        return any(expected_line in normalized_lines for expected_line in expected_lines)

    assert not has_exact_compose_line(
        "ALLOWED_LLM_BASE_URL_HOSTS=ollama,evil.example",
        "ALLOWED_LLM_BASE_URL_HOSTS=ollama",
    )

    for compose in (local_compose, live_compose):
        assert has_exact_compose_line(
            compose,
            'ALLOW_LOCAL_LLM_PROVIDERS: "true"',
            "ALLOW_LOCAL_LLM_PROVIDERS=true",
        )
        assert has_exact_compose_line(
            compose,
            'ALLOWED_LLM_BASE_URL_HOSTS: "ollama"',
            "ALLOWED_LLM_BASE_URL_HOSTS: ollama",
            "ALLOWED_LLM_BASE_URL_HOSTS=ollama",
        )
        assert has_exact_compose_line(
            compose,
            "OPENAI_BASE_URL: http://ollama:11434/v1",
            "OPENAI_BASE_URL=http://ollama:11434/v1",
        )
        assert has_exact_compose_line(
            compose,
            "OPENAI_MODEL: gemma4:e2b-it-qat",
            "OPENAI_MODEL=gemma4:e2b-it-qat",
        )


def test_compose_wrapper_uses_operator_env_file_without_bulk_secret_injection():
    wrapper = (REPO_ROOT / "scripts" / "naruon_compose.sh").read_text()
    gateway_compose = (REPO_ROOT / "docker-compose.gateway.yml").read_text()
    local_compose = (REPO_ROOT / "docker-compose.yml").read_text()

    assert "NARUON_ENV_FILE" in wrapper
    assert "${HOME}/.env" in wrapper
    assert 'docker compose --env-file "${env_file}" "$@"' in wrapper
    assert "env_file:" not in gateway_compose
    assert "env_file:" not in local_compose


def test_postgres_ha_compose_requires_external_postgres_password():
    compose = (REPO_ROOT / "docker-compose.postgres-ha.yml").read_text()

    assert "POSTGRES_PASSWORD:-postgres" not in compose
    assert "${POSTGRES_PASSWORD:?" in compose


def test_kubernetes_backend_database_url_comes_from_secret():
    manifest = (REPO_ROOT / "k8s" / "backend-deployment.yaml").read_text()

    assert "postgres:postgres@" not in manifest
    assert "secretKeyRef" in manifest
    assert "DATABASE_URL" in manifest
    assert "AUTH_SESSION_HMAC_SECRET" in manifest
    assert "auth-session-hmac-secret" in manifest


def test_kubernetes_postgres_password_comes_from_secret():
    manifest = (REPO_ROOT / "k8s" / "db-statefulset.yaml").read_text()

    assert "name: POSTGRES_PASSWORD\n          value: postgres" not in manifest
    assert "secretKeyRef" in manifest
    assert "POSTGRES_PASSWORD" in manifest


def test_env_example_does_not_ship_runtime_secret_defaults():
    env_example = (REPO_ROOT / ".env.example").read_text()

    assert "POSTGRES_DB=" not in env_example
    assert "POSTGRES_USER=" not in env_example
    assert "POSTGRES_PASSWORD=" not in env_example
    assert "DATABASE_URL=" not in env_example
    assert "AUTH_SESSION_HMAC_SECRET=" not in env_example
    assert "ENCRYPTION_KEY=" not in env_example
    assert "postgres:postgres@" not in env_example
    assert "change-me-local-only" not in env_example


def test_readme_uses_cross_platform_browser_command():
    readme = (REPO_ROOT / "README.md").read_text()

    assert "open http://localhost:3000" not in readme
    assert (
        "python -m webbrowser http://localhost:3000" in readme
        or "python3 -m webbrowser http://localhost:3000" in readme
    )
