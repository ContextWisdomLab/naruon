"""Repository contract for PostgreSQL-backed backend acceptance."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_CI = REPO_ROOT / ".github" / "workflows" / "app-ci.yml"
PGVECTOR_CI_IMAGE = (
    "pgvector/pgvector:pg16@"
    "sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b"
)


def _workflow() -> dict[str, object]:
    """Load the workflow without YAML 1.1 coercing the `on` key to a boolean."""
    return yaml.load(APP_CI.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_backend_ci_provisions_migrated_pgvector_database() -> None:
    """Real PostgreSQL tests must run against a ready, migrated CI database."""
    workflow = _workflow()
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    backend = jobs["backend"]
    assert isinstance(backend, dict)

    services = backend.get("services")
    assert isinstance(services, dict), "backend CI must provision PostgreSQL"
    postgres = services.get("postgres")
    assert isinstance(postgres, dict), "backend CI must declare a postgres service"
    assert postgres.get("image") == PGVECTOR_CI_IMAGE
    assert postgres.get("env") == {
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": "test",
        "POSTGRES_DB": "test_db",
    }
    options = postgres.get("options")
    assert isinstance(options, str)
    assert "pg_isready -U test -d test_db" in options

    environment = backend.get("env")
    assert isinstance(environment, dict)
    assert environment.get("DATABASE_URL") == (
        "postgresql+asyncpg://test:test@localhost:5432/test_db"
    )
    assert "AUTH_SESSION_HMAC_SECRET" not in environment, (
        "CI runtime auth material must be generated per job, not committed as a fixture"
    )

    steps = backend.get("steps")
    assert isinstance(steps, list)
    named_steps = {
        step.get("name"): step
        for step in steps
        if isinstance(step, dict) and isinstance(step.get("name"), str)
    }
    runtime_secret = named_steps.get("Generate ephemeral CI runtime secret")
    assert isinstance(runtime_secret, dict), (
        "backend CI must generate auth material before importing runtime settings"
    )
    runtime_secret_script = str(runtime_secret.get("run", ""))
    assert "secrets.token_urlsafe(48)" in runtime_secret_script
    assert "AUTH_SESSION_HMAC_SECRET" in runtime_secret_script
    assert "GITHUB_ENV" in runtime_secret_script
    assert 'print(f"::add-mask::{value}")' in runtime_secret_script, (
        "generated runtime auth material must be masked before later steps expose env"
    )
    assert runtime_secret_script.index("::add-mask::") < runtime_secret_script.index(
        "GITHUB_ENV"
    )

    migration = named_steps.get("Run database migrations")
    assert isinstance(migration, dict), "backend CI must migrate before pytest"
    assert "python scripts/migrate_db.py" in str(migration.get("run", ""))

    step_names = [
        step.get("name") for step in steps if isinstance(step, dict) and step.get("name")
    ]
    assert step_names.index("Generate ephemeral CI runtime secret") < step_names.index(
        "Run database migrations"
    ) < step_names.index("Run backend tests")
