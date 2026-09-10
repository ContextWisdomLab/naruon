# Starlette TestClient `httpx2` dependency

## Observed failure

Protected `develop@042b0c70531b229af3acbd0421a2f23098d848b3` pins Starlette
1.3.1 but did not install `httpx2`. Importing `starlette.testclient` therefore
fell back to deprecated `httpx`; warning-as-error test runs stopped during
collection. Removing the warning filter without installing the preferred
transport would expose the defect without repairing it.

## Decision and boundary

Pin `httpx2==2.5.0` in the repository's existing combined backend
development/direct-test manifests and immutable locks. Keep application HTTP
clients on their existing `httpx` path. A runtime regression test imports
Starlette's TestClient module and verifies that its selected transport module is
`httpx2`; manifest and digest checks alone are insufficient evidence.

Starlette 1.2.0 introduced TestClient support for `httpx2`, and 1.3.0 added it
to the `full` extra. The 2.5.0 wheel in this change matches PyPI's published
SHA-256 digest `3d2d4d9cf4b61f1a1f46a95947cfdb47e80cb56a2f91c6256ac8f58e4891df41`.
PyPI records a trusted-publishing attestation from the `pydantic/httpx2`
repository at tag `v2.5.0`. These facts establish origin and integrity; they do
not transfer current-head CI or protected-merge authority.

## Verification and rollback

Run from `backend/`:

```bash
uv run --frozen pytest -q -W error tests/test_container_dependency_pin_contract.py
uv run --frozen ruff check tests/test_container_dependency_pin_contract.py
```

Rollback removes the direct pin, regenerated lock records, runtime assertion,
and obsolete-warning-filter removal together. Do not restore only the warning
suppression.

## References

Kludex. (2026). *Starlette release notes*. GitHub.
https://github.com/Kludex/starlette/blob/main/docs/release-notes.md

Python Packaging Authority. (2026). *httpx2 2.5.0 file details and provenance*.
PyPI. https://pypi.org/project/httpx2/2.5.0/

Pydantic. (2026). *HTTPX2 v2.5.0* [Source code]. GitHub.
https://github.com/pydantic/httpx2/tree/v2.5.0
