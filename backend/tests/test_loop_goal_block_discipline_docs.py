from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _read_repository_document(path: str) -> str:
    return (_REPOSITORY_ROOT / path).read_text(encoding="utf-8")


def test_agents_documents_non_terminal_wait_and_permission_boundaries() -> None:
    agents_text = _read_repository_document("AGENTS.md")

    assert "## Loop-goal block discipline and local development authority" in agents_text
    assert "states, not top-level blockers" in agents_text
    assert '"no side-effect-free step left"' in agents_text
    assert "Never trial-run a forbidden action to check permissions." in agents_text
    assert "opencode_loop_goal_blocked" in agents_text
    assert "Candidate `reason`/`needed`/`evidence` strings are not approved" in agents_text
    assert "Never treat a candidate tool call's success as verification passed" in agents_text
    assert "nor fake progress to reset the" in agents_text


def test_claude_documents_same_high_level_blocking_contract() -> None:
    claude_text = _read_repository_document("CLAUDE.md")

    assert "## Loop-goal block discipline and local development authority" in claude_text
    assert "states, not top-level blockers" in claude_text
    assert '"no side-effect-free step left"' in claude_text
    assert "opencode_loop_goal_blocked" in claude_text
    assert "effective `ask`/`deny` rules take precedence" in claude_text


def test_loop_discipline_inherits_canonical_llm_owner_guidance() -> None:
    agents_text = _read_repository_document("AGENTS.md")
    claude_text = _read_repository_document("CLAUDE.md")

    assert "do not add repository-local `opencode.json` or `opencode.jsonc`" in agents_text
    assert "provider/model routing belongs to `contextual-orchestrator`" in claude_text
