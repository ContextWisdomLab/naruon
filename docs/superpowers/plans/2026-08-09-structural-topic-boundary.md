# Structural Topic Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove keyword-triggered pseudo-topic classification from Naruon's
product surface and document the fail-closed TEPP STM boundary.

**Architecture:** Naruon's generic tool registry will retain honest lexical
utilities but will no longer expose fixed dictionaries as topic inference or
agenda generation. Corpus-level STM remains an external Rust-first TEPP
measurement boundary whose future posterior contract is documented here rather
than simulated in the request handler.

**Tech Stack:** Python 3.12+, FastAPI tool registry, pytest, Ruff, Markdown.

## Global Constraints

- Do not introduce keyword, embedding, or LLM fallback topic classification.
- Do not claim that a fixed business label is an STM posterior probability.
- Preserve `ANALYSIS_TEXT_MAX_CHARS` enforcement for the retained lexical tool.
- Treat every warning as a verification failure.
- Keep the change atomic and avoid unrelated tool-registry refactoring.

- [x] **Preflight: read the repository root `AGENTS.md` completely before any
  change.**

---

### Task 1: Lock out lexical pseudo-topic tools

**Files:**
- Modify: `backend/tests/test_tools_api.py`
- Modify: `backend/api/tools.py`

**Interfaces:**
- Consumes: the existing module-level `registry: ToolRegistry`.
- Produces: a registry without `email_categorizer` or
  `meeting_agenda_generator`; `keyword_extractor` remains registered and is
  explicitly described as term-frequency extraction.

- [x] **Step 1: Write the failing registry-contract test**

```python
@pytest.mark.parametrize(
    "tool_code", ["email_categorizer", "meeting_agenda_generator"]
)
def test_registry_omits_lexical_pseudo_topic_tools(tool_code):
    assert registry.get(tool_code) is None


def test_keyword_extractor_is_disclosed_as_lexical_term_frequency():
    tool = registry.get("keyword_extractor")
    assert tool is not None
    assert tool.description == (
        "텍스트 본문에서 빈도와 최초 출현 순으로 반복 용어를 추출합니다."
    )
```

- [x] **Step 2: Run the focused tests and verify RED**

Run:
`PYTHONWARNINGS=error DISABLE_BACKGROUND_WORKERS=1 python -m pytest backend/tests/test_tools_api.py::test_registry_omits_lexical_pseudo_topic_tools backend/tests/test_tools_api.py::test_keyword_extractor_is_disclosed_as_lexical_term_frequency -q`

Expected: the first test fails because both pseudo-topic tools are registered;
the second fails because the current description overclaims importance.

- [x] **Step 3: Remove the pseudo-model implementation**

Delete `_CATEGORY_TERMS`, `_AGENDA_TOPICS`, `_contains_analysis_term`, both
handlers, both `registry.register(...)` blocks, and their behavior-locking tests.
Change the retained handler docstring to
`"""Extract deterministic lexical terms by frequency and first occurrence."""`
and its tool description to
`"텍스트 본문에서 빈도와 최초 출현 순으로 반복 용어를 추출합니다."`.

- [x] **Step 4: Run the focused test file and verify GREEN**

Run:
`PYTHONWARNINGS=error DISABLE_BACKGROUND_WORKERS=1 python -m pytest backend/tests/test_tools_api.py -q`

Expected: all tests pass with no warning-class output.

### Task 2: Record the scientific and governance boundary

**Files:**
- Modify: `AGENTS.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/adr/README.md`
- Create: `docs/adr/0001-topic-measurement-authority.md`
- Create: `docs/doctoring/structural-topic-model-boundary.md`

**Interfaces:**
- Consumes: the decision in
  `docs/superpowers/specs/2026-08-09-structural-topic-boundary-design.md`.
- Produces: a durable anti-pattern rule, user-visible change record, and APA 7
  research note.

- [x] **Step 1: Add the anti-pattern rule**

State that topic inference must not be implemented with hard-coded term lists,
term frequency, embeddings, or LLM labels presented as STM; unavailability of a
fitted TEPP model must fail closed.

- [x] **Step 2: Add the changelog entry**

Under the current unreleased section, record removal of the two misleading tools
and preservation of the honest lexical utility.

- [x] **Step 3: Add the doctoring note**

Document the defect history, distinction between STM and classification, future
TEPP contract, and APA 7 references. Check redistribution permission for each
relevant paper: commit the PDF only when redistribution is permitted; otherwise
include its citation, DOI link, and a concise summary of how it supports the
boundary. Permission was not established for the two cited articles, so this PR
uses citations, links, and summaries rather than copies.

### Task 3: Complete the decision-to-operation documentation graph

**Files:**
- Modify: `README.md`, `ARCHITECTURE.md`, `CLAUDE.md`, `CHANGELOG.md`
- Modify: `docs/planning/naruon-platform-plan.md`
- Modify: the boundary design and this implementation plan
- Create: companion ADRs and `docs/topic-intelligence/` requirements,
  architecture, contract/schema, UML, conceptual ERD, security, threat, test,
  operability, traceability, references, and fitness records
- Create: `backend/tests/test_topic_intelligence_documentation.py`

- [x] **Step 1: Audit the pre-change documentation set**

Record whether each requested artifact exists, is discoverable, is internally
consistent, and distinguishes implemented behavior from a planned contract.

- [x] **Step 2: Add the missing or stale records**

Make the deletion decision reviewable and the future integration discoverable,
without claiming a runtime endpoint, physical topic persistence, accepted TEPP
contract, or reproducible replay where only digests are available.

- [x] **Step 3: Add machine-readable fitness checks**

Validate required files and links, schema revision/ownership/status markers,
error-versus-abstention semantics, conceptual-only data modeling, sensitive
digest treatment, and removal of stale platform-plan claims.

### Task 4: Verify and publish

**Files:**
- Verify all files changed by Tasks 1 and 2.

**Interfaces:**
- Consumes: the completed atomic diff.
- Produces: exact local evidence and a GitHub pull request based on the current
  `develop` head.

- [x] **Step 1: Run Ruff**

Run:
`python -m ruff check backend/api/tools.py backend/tests/test_tools_api.py backend/tests/test_topic_intelligence_documentation.py`

Expected: exit 0 and no diagnostics.

Observed on the complete candidate tree: Ruff passed for the affected tool and
documentation-fitness test files.

- [x] **Step 2: Run the complete backend suite**

Run:
`PYTHONWARNINGS=error DISABLE_BACKGROUND_WORKERS=1 python -m pytest backend -q`

Expected: exit 0 with no `Timeout`, `Fatal`, `Warn`, or `Denied` output.

Observed after merging the protected-base security remediation, with proxy
variables removed: `1711 passed, 33 skipped`; the focused tool/documentation
suite reported `79 passed`.

- [x] **Step 3: Inspect the exact diff**

Run: `git diff --check`, `git diff --stat`, and compare the exact changed paths
against this allowlist (including every file under `docs/topic-intelligence/`):

```text
AGENTS.md
ARCHITECTURE.md
CHANGELOG.md
CLAUDE.md
README.md
backend/api/tools.py
backend/tests/test_tools_api.py
backend/tests/test_topic_intelligence_documentation.py
docs/adr/0001-topic-measurement-authority.md
docs/adr/0002-fitted-topic-artifact-consumption.md
docs/adr/0003-separate-topic-measurement-from-agenda-generation.md
docs/adr/README.md
docs/doctoring/structural-topic-model-boundary.md
docs/planning/naruon-platform-plan.md
docs/superpowers/plans/2026-08-09-structural-topic-boundary.md
docs/superpowers/specs/2026-08-09-structural-topic-boundary-design.md
docs/topic-intelligence/API_CONTRACT.md
docs/topic-intelligence/ARCHITECTURE.md
docs/topic-intelligence/DATA_MODEL.md
docs/topic-intelligence/DOCUMENTATION_FITNESS.md
docs/topic-intelligence/OPERABILITY.md
docs/topic-intelligence/PRD.md
docs/topic-intelligence/README.md
docs/topic-intelligence/REFERENCES.md
docs/topic-intelligence/SECURITY.md
docs/topic-intelligence/TEST_STRATEGY.md
docs/topic-intelligence/THREAT_MODEL.md
docs/topic-intelligence/TRACEABILITY.md
docs/topic-intelligence/TRD.md
docs/topic-intelligence/UML.md
docs/topic-intelligence/schema/topic-inference-result-v1.schema.json
```

Expected: no whitespace errors; only the scoped source, tests, governance, and
research/design documents changed.

Observed: `git diff --check` passed and the complete base-to-candidate plus
working-tree path set exactly matched all 31 allowlisted paths.

- [x] **Step 4: Commit and open a pull request**

The predecessor source/test head passed local validation and PR #1297 was
opened. Its body must distinguish predecessor evidence from eventual exact-head
evidence and link the current-head CI, security, and review results before
merge. Push documentation and review fixes to the same
`fix/remove-lexical-topic-heuristics` branch; do not open a duplicate PR.
