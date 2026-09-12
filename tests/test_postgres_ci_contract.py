"""Repository contract for PostgreSQL-backed backend acceptance."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_CI = REPO_ROOT / ".github" / "workflows" / "app-ci.yml"


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
    assert postgres.get("image") == "pgvector/pgvector:pg16"
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

    steps = backend.get("steps")
    assert isinstance(steps, list)
    named_steps = {
        step.get("name"): step
        for step in steps
        if isinstance(step, dict) and isinstance(step.get("name"), str)
    }
    migration = named_steps.get("Run database migrations")
    assert isinstance(migration, dict), "backend CI must migrate before pytest"
    assert "python scripts/migrate_db.py" in str(migration.get("run", ""))

    step_names = [
        step.get("name") for step in steps if isinstance(step, dict) and step.get("name")
    ]
    assert step_names.index("Run database migrations") < step_names.index(
        "Run backend tests"
    )
