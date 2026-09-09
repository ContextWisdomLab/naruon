# Provenance restore and migration evidence

## Status and customer consequence

Proposed; observed 2026-09-05. No protected merge, release, or live customer
restore is claimed. A customer must be able to install Naruon before importing
portable evidence. Passing import tests against ORM-created tables did not
establish that prerequisite: the actual fresh installation failed first.

## Exact revisions and observations

| Lane | Full source head | Observation |
| --- | --- | --- |
| #1497 provenance | `705d8ece2c97edc8575ea59766fd8f68bf4cdb82` | 224 PostgreSQL-backed suite tests passed, zero skipped; strict `-W error` rerun also passed. Fresh Alembic upgrade failed, exit 1. |
| #1502 CI proposal | `0b9e324a91fd2148b2b2759cca875ac7d50c86a0` | Fresh and repeat upgrades reached `0017_merge_newsdom_carddav_heads`; 64 focused tests passed in the existing local environment. Not clean-lock or stamped-forward-repair evidence. |
| #1503 before integration | `9c1851336fa04bcdc77c1c6e531afdb882583af1` | 73 tests passed with a retained, undeclared httpx2 package. Exact synchronization removed it; strict Data API collection then failed, exit 4. |
| #1565 dependency owner | `52dfc863d1a5d6e4e80b6366f719dd09f2aa6172` | Existing declared httpx2 dependency, lock, warning-suppression removal, and runtime regression delta; reused unchanged. |
| #1503 integrated owner | `19d5860bc27e860acba940390f5792721cd99e5e` | Tree `793aadd78a7ad2d6033ca6e12a931dfa776b7374`: exact synchronization, fresh/repeat upgrade to `0019_email_read_state_repair`, 75 tests with `-W error`, Ruff and diff checks passed. |
| #1468 before search repair | `037b58adeda53e6c847f8949494b9b518a94dac9` | Normal merge of #1503, unique bootstrap assertion retained; exact sync, fresh/repeat 0019 and 75 strict PostgreSQL tests passed, zero skipped. |
| #1427 before search repair | `02366791b2a449b8b23b527dcc550996361c0f96` | Normal merge of #1468; exact sync, fresh/repeat 0019 and 76 strict PostgreSQL tests passed, zero skipped. Naruon 64 MiB admission is not immutable NewsDOM release evidence. |
| #1572 search-storage owner | `cd8ff413d4ed8a5f2855c47a21a31db5661cd487` | Tree `526b7c334a00020e5f3ac49d76d3fdd2b44a9665`, based on #1503: four GiST regression failures become 131 strict PostgreSQL passes after forward GIN revision 0020. Representative latency and migration-cost gates remain open. |
| #1468 current propagated owner | `53ce38ed6683d01a9d113069f5ac5a8f17e133a2` | Tree `723d9f4b4d503cf19b67d473a8d5398b7b0dd114`: normal merge of #1572, fresh/repeat 0020 and 131 strict PostgreSQL/search tests passed, zero skipped. |
| #1427 current PDF lane | `cb08b1c3ea2aba8844fc29ef703c34368cc55e47` | Tree `526ba4181a710f96f61a1347720d606bdf92aa0f`: normal merge of #1468, fresh/repeat 0020 and 132 strict tests passed, zero skipped. ADR-0021 retains the colliding 0005 proposal. |
| #1497 current combined restore | `69f50ae684f50c501ff2f49be2969f1d211d7f3c` | Tree `839d62316b5ff5f1e84e346e48982f0d4494c8c7`: normal merge of #1427; fresh/repeat 0021 and 345 strict tests passed, zero skipped, including unchanged large content, rollback identity, and incompatible writers. ADR-0022 retains the colliding 0007 proposal. |
| #1469 current source-retention integration | `1b757d5aa25c469157f8f03301964eb3061ed0fe` | Tree `6b520c3cbe824d4017b97c39ef61fa702434e04a`: normal integration preserves #1427, concurrent `facadfb1` and `db083c9`, then adopts provider HTTP 413 classification; clean-lock fresh/repeat 0020 and 277 strict tests passed, zero failures/errors/skips. Real 40,758,835-byte PDF sources survive pending, size rejection, rollback and next-item continuation. No recognition/capacity/release claim. |

The #1503 commit has the before-integration and #1565 heads as its two parents;
neither history was rewritten. The verified pre-commit tree exactly matches
the committed tree. Its direct PR base is #1565, not protected `develop`.
All current lane rows are pushed source heads. Earlier intermediate results
below are retained as causal history and do not override the current receipt.

The #1469 [exact-head source-retention receipt](https://github.com/ContextualWisdomLab/naruon/blob/1b757d5aa25c469157f8f03301964eb3061ed0fe/docs/doctoring/bounded-attachment-parse-source-contract.md)
adds an actual worker exception-path check to manual transaction rollback.
Two persisted records expose SQLAlchemy expiration after the first transaction
is deliberately aborted: both attachment and document variants first fail with
`MissingGreenlet`. Cache primitive IDs before processing and explicitly reload
remaining pending records after rollback; no new query runs on the normal path.
The focused 29-test receipt and earlier `db083c9` combined 276-test receipt are
separate. The later provider HTTP 413 test/fix is normally inherited at
`1b757d5`; its own complete suite passes 277 tests in 73.71 s after exact
dependency sync and fresh/repeat migration. JUnit SHA-256:
`5ec09d7152e0f3551fa670ac15567282ae02ac71170cd51eb5e3e51433abab10`.
The HTTP 413 response is a unit MockTransport case, not real network evidence.
Complete retained bytes and stable identities are checked in fresh
sessions with migration-created indexes enabled. The intentional fault log is
asserted, not suppressed or misrepresented as successful provider execution.
ADR-0023 remains Proposed; owner releases, realistic capacity, signed HTTP and
browser paths, current-head Checks and independent approval remain open.

## Subsequent migrated integration and search-storage finding

The first local #1497 merge of remote head
`705d8ece2c97edc8575ea59766fd8f68bf4cdb82` with #1427
`02366791b2a449b8b23b527dcc550996361c0f96` reconciles the bootstrap owner
conflicts and adds an unpublished revision joining the two Alembic heads.
Fresh and repeat migrations pass. A real rollback first exposed destruction
of retained portable-identity mappings; the unmerged proposal now retains them,
and historical/downgrade/re-upgrade cases pass. Two forced-overlap transaction
tests cover identical and incompatible imports, including one rejected writer,
intact winning content, and no losing rows or mappings for incompatible input.

That intermediate actual-migration suite reported **1 failed / 288 passed**.
`test_export_counts_cited_segment_bytes_once` stores its unchanged 8 MiB-class
high-entropy segment and fails with SQLSTATE `54000`: the whole-document GiST
leaf exceeds PostgreSQL's index-row limit. Shrinking the value, omitting the
index, or returning to ORM-only tables would conceal this separate defect.
The local checkpoint `7ee6e68c31b2e716210fc8b62e287a78b765062b` recorded
that known failure and was not presented as a passing integration.

Current #1497 `69f50ae684f50c501ff2f49be2969f1d211d7f3c` then normally
inherits #1427 `cb08b1c3ea2aba8844fc29ef703c34368cc55e47`. Fresh/repeated
upgrade reaches the single `0021_merge_provenance_workspace` head and the
unchanged large archive case now passes within **345 passed, zero failed/skipped**
with `-W error` in 176.52 seconds. Both the test command and exact-project cleanup
exit zero. Its [combined receipt](https://github.com/ContextualWisdomLab/naruon/blob/69f50ae684f50c501ff2f49be2969f1d211d7f3c/docs/doctoring/tenant_provenance_integration.md)
records the reproducible command, complete source lineage, and local artifact
hashes. This result is not signed HTTP/browser restore, production performance,
or a current-head protected gate.

Naruon owns those schema-bound search expressions. New Draft
[#1572](https://github.com/ContextualWisdomLab/naruon/pull/1572) on #1503
provides a forward full-content GIN storage candidate; RankWeave's fusion and
normalization ownership is unchanged. GIN does not provide distance-only kNN
acceleration, so this candidate is not accepted until representative query and
migration costs are measured and any findings repaired. Its
[Proposed ADR-0020](https://github.com/ContextualWisdomLab/naruon/blob/cd8ff413d4ed8a5f2855c47a21a31db5661cd487/docs/adr/0020-full-document-trigram-storage.md)
and [131-test receipt](https://github.com/ContextualWisdomLab/naruon/blob/cd8ff413d4ed8a5f2855c47a21a31db5661cd487/docs/doctoring/search_trigram_storage.md)
preserve the causal probe, alternatives, primary references, image digest,
index-presence assertion, and rollback limitations. The unchanged #1497 large
archive regression passed after inheritance; the smaller diagnostic
supplements it rather than replacing acceptance coverage.

## Root cause and rejected shortcuts

At historical #1497 head `705d8ece2c97edc8575ea59766fd8f68bf4cdb82`,
`backend/tests/test_tenant_provenance_bundle.py` prepares tables using
`Base.metadata.create_all()`. That exercises the current models but does not
traverse the Alembic revision graph. Actual `scripts/migrate_db.py` execution
stops in `backend/alembic/versions/0011_email_read_state.py`:

```text
asyncpg.exceptions.UndefinedTableError: relation "emails" does not exist
ALTER TABLE emails ADD COLUMN is_read BOOLEAN DEFAULT true NOT NULL
```

The current table is `email_records`. Creating a fake `emails` table, stamping
past the failed revision, suppressing the exception, or copying a repair into
the provenance service would conceal the installation defect. Existing #1503
owns both the guarded historical path and forward
`0019_email_read_state_repair` for already-stamped databases. Editing an applied
revision alone cannot cause Alembic to replay it.

A second verification defect came from local package state. `uv run --frozen`
retained `httpx2==2.5.0` even though #1503 did not declare it. Exact
`uv sync --locked` in that task-owned worktree removed the extra package.
Strict TestClient collection then produced `ModuleNotFoundError: No module
named 'httpx2'` and Starlette's deprecation warning. Reusing #1565 fixed the
declared dependency; reinstalling it manually would have hidden the same gap.
`PYTHONWARNINGS=error` alone also does not neutralize pytest ignore rules.
Explicit `-W error` is used for the repaired receipt; marks and intentional
warning-catching test contexts still need review.

## Verification procedure and scope

Each database run used its own Compose project, a free `127.0.0.1` host port,
random test-only credentials, read-only root filesystem, no-new-privileges,
256 MiB shared memory, and tmpfs database storage. The installed image was
`pgvector/pgvector@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b`
(PostgreSQL 16.15, aarch64). Each exact project was removed by its exit trap;
pre-existing services and persistent volumes were not changed. Credential
values were not printed or committed. Logs and the Compose input remain local
under `/private/tmp/naruon-provenance-pg.5wO5pq`; that path is not a hosted artifact.

From the integrated #1503 `backend/` directory, with the disposable database
URL and fresh bootstrap secret supplied only for the test process:

```sh
uv sync --locked
uv run --frozen python scripts/migrate_db.py
uv run --frozen python scripts/migrate_db.py
uv run --frozen python -m pytest -q -W error -ra --tb=short \
  tests/test_alembic_migrations.py tests/test_bootstrap_db.py \
  tests/test_data_api.py tests/test_email_read_state_migration_postgres.py \
  tests/test_legacy_document_scope_postgres.py \
  tests/test_workspace_document_migration.py \
  tests/test_container_dependency_pin_contract.py
```

Both migration commands exited zero; a read-only `SELECT version_num FROM
alembic_version` returned `0019_email_read_state_repair`. The suite returned
75 passed, zero failed/skipped. Historical read-state repair, pre-registry
installation, already-stamped repair, document scope, and data-preserving
downgrade paths run actual PostgreSQL; fast API tests remain mocked where their
fixtures say so. This is local source-tree evidence, not hosted gate evidence.

On #1497, the provenance and Data API command is:

```sh
uv run --frozen python -m pytest -q -W error -ra --tb=short \
  tests/test_tenant_provenance_bundle.py tests/test_data_api.py
```

That run passed 224 tests in 12.53 seconds, zero skipped, with real database
service tests. Its environment retained other packages outside the lock, so
do not promote it to clean-lock proof. API success tests replace the service;
they do not prove signed HTTP-to-database restore. Concurrent successful imports
were covered at that historical head. Forced incompatible-overlap coverage has
since passed in the now-pushed integration described above; it is not a hosted
or protected source receipt.

## Dependency decision and next actions

1. Keep #1503 on #1565 and Draft until current-head hosted gates and qualifying
   independent review pass. This supersedes the historical
   [#1502-before-#1503 proposal](https://github.com/ContextualWisdomLab/naruon/pull/1503#issuecomment-5503791028);
   it does not create reciprocal prerequisites or close either PR.
2. #1572 is now propagated and pushed through #1468, #1427, and #1497 with
   their unique deltas intact. Preserve that ancestry and the 345-test receipt
   while obtaining each head's own required Checks/review. Do not transfer one
   lane's approval or runtime evidence to another head.
3. The combined graph now ends at `0021_merge_provenance_workspace`, joining
   provenance identity and search storage. Keep #1572 Draft until representative
   query and migration costs are verified and repaired as needed. Continue the
   signed HTTP/browser restore acceptance path; the passing service tests do
   not replace it. Let #1469 inherit #1427's ADR-0021 rename normally, preserving
   its former proposal identity and other unique parser delta.
4. #1502 remains the CI-service lane on #1562, whose own parent is #1531.
   Integrate the existing #1503 forward repair by ancestry rather than copying
   `0019` to answer its [already-stamped database finding](https://github.com/ContextualWisdomLab/naruon/pull/1502#discussion_r3939592974).
5. AGENTS.md recurrence rules are owned by #1566
   (`498cf0ca7d25b777a7dafa6bcc839df164babfd0`), not repeated in product PRs.
   Its migrated-schema, full-size-content, and retained-identity rollback rules
   now cover these findings. Forty-four focused source/governance tests pass
   in the existing environment, not a clean-lock or database acceptance run.
   Former body-only confidence and tool-mutation rules are now proposed source;
   normal merges preserve both concurrent documentation and source-guard deltas.
   Current queued checks are wait states; neither a local pass nor PR metadata
   promotes Proposed work to a released or protected contract.

## Retained local artifact integrity

Hashes identify local receipts; they do not substitute for hosted retention.

| File under the local evidence directory | SHA-256 |
| --- | --- |
| `migration_fresh.log` (#1497 failure) | `2091d0064e3c341bf702a72cd7dc24763389b4127ff130419771e2ff7c728993` |
| `strict_provenance_test_results.xml` | `984b7de41a23f381ac6590daeedd8f09e4088fda4ab7e98601eca214d6982ba2` |
| `clean_lock_owner_testclient.log` | `91e82b377204c42bda20f6789a08230a7119ab6ed9e753dbbc8f4d83a229cd8c` |
| `integrated_migration_fresh.log` | `af944edcbac788fa25e2038e7716b435526e4227a6c3afeaba7ac1c1fdaf567d` |
| `integrated_owner_test_results.xml` | `d8fd58d035a40e19ab977122c21011f49df93b0527ba8d08fac34297197269a9` |

## References (APA 7th)

Alembic developers. (n.d.). *Tutorial*. Retrieved September 5, 2026, from https://alembic.sqlalchemy.org/en/latest/tutorial.html

Astral. (n.d.). *Locking and syncing*. Retrieved September 5, 2026, from https://docs.astral.sh/uv/concepts/projects/sync/

Docker, Inc. (n.d.). *Define services in Docker Compose*. Retrieved September 5, 2026, from https://docs.docker.com/reference/compose-file/services/

Docker, Inc. (n.d.). *Port publishing and mapping*. Retrieved September 5, 2026, from https://docs.docker.com/engine/network/port-publishing/

pytest developers. (n.d.). *How to capture warnings*. Retrieved September 5, 2026, from https://docs.pytest.org/en/stable/how-to/capture-warnings.html
