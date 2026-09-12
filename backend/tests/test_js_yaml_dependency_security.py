"""Keep the generated frontend dependency graph on the reviewed js-yaml floor."""

from pathlib import Path

import yaml


FRONTEND_ROOT = Path(__file__).resolve().parents[2] / "frontend"
JS_YAML_PATCHED_RELEASE = "4.3.2"


def _resolved_version(package_key: str) -> tuple[int, int, int]:
    """Return the semantic version from one peer-qualified js-yaml lock key."""

    prefix = "js-yaml@"
    assert package_key.startswith(prefix)
    version = package_key[len(prefix) :].split("(", 1)[0]
    return tuple(int(part) for part in version.split("."))


def test_js_yaml_override_lock_and_eslint_consumer_share_patched_release() -> None:
    """Bind workspace policy, generated lock identity, and the ESLint consumer together."""

    workspace = yaml.safe_load(
        (FRONTEND_ROOT / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    )
    lock = yaml.safe_load(
        (FRONTEND_ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8")
    )

    assert str(workspace["overrides"]["js-yaml"]) == JS_YAML_PATCHED_RELEASE
    assert str(lock["overrides"]["js-yaml"]) == JS_YAML_PATCHED_RELEASE

    floor = (4, 3, 2)
    for section_name in ("packages", "snapshots"):
        keys = [key for key in lock[section_name] if key.startswith("js-yaml@")]
        assert keys, f"{section_name} must contain a js-yaml resolution"
        assert {_resolved_version(key) for key in keys} == {floor}

    eslint_snapshots = [
        value
        for key, value in lock["snapshots"].items()
        if key.startswith("@eslint/eslintrc@")
    ]
    assert eslint_snapshots, "lock must retain the ESLint configuration snapshot"
    assert any(
        str(snapshot.get("dependencies", {}).get("js-yaml"))
        == JS_YAML_PATCHED_RELEASE
        for snapshot in eslint_snapshots
    ), "ESLint must consume the reviewed js-yaml release"
