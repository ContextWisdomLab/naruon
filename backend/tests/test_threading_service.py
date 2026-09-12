import pytest

from services.threading_service import (
    _find_existing_thread_ids,
    assign_thread_id,
    extract_reference_ids,
    generate_email_fingerprint,
    normalize_message_id,
)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _SequentialSession:
    def __init__(self, values):
        self._values = list(values)
        self.execute_count = 0

    async def execute(self, _query):
        self.execute_count += 1
        rows = self._values.pop(0) if self._values else []
        return _Result(rows)


class _QueryCapturingSession(_SequentialSession):
    def __init__(self, values):
        super().__init__(values)
        self.queries = []

    async def execute(self, query):
        self.queries.append(query)
        return await super().execute(query)


@pytest.mark.asyncio
async def test_reply_before_root_uses_first_reference_as_deterministic_thread_id():
    session = _SequentialSession([[]])

    thread_id = await assign_thread_id(
        session,
        {
            "message_id": "<reply@example.com>",
            "in_reply_to": "<parent@example.com>",
            "references": "<root@example.com> <parent@example.com>",
        },
        user_id="testuser",
        organization_id="org-acme",
        workspace_id="workspace-a",
    )

    assert thread_id == "root@example.com"


@pytest.mark.asyncio
async def test_reply_without_references_uses_in_reply_to_as_deterministic_thread_id():
    session = _SequentialSession([[]])

    thread_id = await assign_thread_id(
        session,
        {
            "message_id": "<reply@example.com>",
            "in_reply_to": "<parent@example.com>",
            "references": None,
        },
        user_id="testuser",
        organization_id="org-acme",
        workspace_id="workspace-a",
    )

    assert thread_id == "parent@example.com"


@pytest.mark.asyncio
async def test_existing_parent_thread_id_wins_over_deterministic_fallback():
    session = _SequentialSession([[("<parent@example.com>", "thread-123")]])

    thread_id = await assign_thread_id(
        session,
        {
            "message_id": "<reply@example.com>",
            "in_reply_to": "<parent@example.com>",
            "references": "<root@example.com> <parent@example.com>",
        },
        user_id="testuser",
        organization_id="org-acme",
        workspace_id="workspace-a",
    )

    assert thread_id == "thread-123"


@pytest.mark.asyncio
async def test_existing_legacy_bracketed_thread_id_is_normalized():
    session = _SequentialSession([[("<root@example.com>", "<root@example.com>")]])

    thread_id = await assign_thread_id(
        session,
        {
            "message_id": "<reply@example.com>",
            "in_reply_to": "<root@example.com>",
            "references": "<root@example.com>",
        },
        user_id="testuser",
        organization_id="org-acme",
        workspace_id="workspace-a",
    )

    assert thread_id == "root@example.com"


@pytest.mark.asyncio
async def test_forwarded_subject_alone_does_not_merge_unrelated_thread():
    session = _SequentialSession([[("unrelated@example.com", "unrelated-thread")]])

    thread_id = await assign_thread_id(
        session,
        {
            "message_id": "<forwarded-copy@example.com>",
            "in_reply_to": None,
            "references": None,
            "subject": "Fwd: Q2 출시 계획",
        },
        user_id="testuser",
        organization_id="org-acme",
        workspace_id="workspace-a",
    )

    assert thread_id == "forwarded-copy@example.com"
    assert session.execute_count == 0


@pytest.mark.asyncio
async def test_existing_thread_lookup_is_scoped_to_owner_and_organization():
    session = _QueryCapturingSession([[("<parent@example.com>", "thread-123")]])

    thread_id = await assign_thread_id(
        session,
        {
            "message_id": "<reply@example.com>",
            "in_reply_to": "<parent@example.com>",
            "references": None,
        },
        user_id="testuser",
        organization_id="org-acme",
        workspace_id="workspace-a",
    )

    assert thread_id == "thread-123"
    query_text = str(session.queries[-1]).lower()
    assert "email_records.user_id" in query_text
    assert "email_records.organization_id" in query_text
    assert "email_records.workspace_id" in query_text


def test_normalize_message_id_strips_brackets_and_outer_whitespace():
    assert normalize_message_id("<abc@example.com>") == "abc@example.com"
    assert normalize_message_id("  <abc@example.com>  ") == "abc@example.com"
    assert normalize_message_id("< abc@example.com >") == "abc@example.com"
    assert normalize_message_id("<<abc@example.com>>") == "abc@example.com"
    assert normalize_message_id("abc@example.com") == "abc@example.com"


def test_normalize_message_id_handles_empty_and_none():
    assert normalize_message_id(None) is None
    assert normalize_message_id("") is None
    assert normalize_message_id("   ") is None
    assert normalize_message_id("<>") is None


def test_normalize_message_id_collapses_interior_unfolding_whitespace():
    # RFC 5322 section 2.2.3 header unfolding can leave interior whitespace when
    # a folded Message-ID is rejoined; RFC 5322 section 3.6.4 msg-id carries
    # none, so the folded and unfolded forms must normalize to the same value or
    # dedup/threading would treat one message as two.
    canonical = normalize_message_id("<abc@example.com>")
    assert normalize_message_id("<abc@ example.com>") == canonical
    assert normalize_message_id("<abc @example.com>") == canonical
    assert normalize_message_id("<abc@\r\n example.com>") == canonical
    assert normalize_message_id("<abc@\texample.com>") == canonical


def test_extract_reference_ids_normalizes_folded_whitespace_and_dedupes():
    header = "<a@x.com> <a@ x.com>\r\n <b@x.com>"
    # The first two are the same id split over a fold boundary, so only two
    # distinct references remain, in header order.
    assert extract_reference_ids(header) == ["a@x.com", "b@x.com"]


def test_extract_reference_ids_drops_bracketed_whitespace_only_ids():
    # "< >" / "<\t>" are bracketed but whitespace-only: they normalize to nothing
    # and must be dropped, not carried as empty thread candidates.
    assert extract_reference_ids("< > <a@x.com> <\t>") == ["a@x.com"]


def test_extract_reference_ids_falls_back_to_whitespace_split_without_brackets():
    # A References value with no angle brackets (some non-conforming clients)
    # falls back to a whitespace split rather than yielding nothing.
    assert extract_reference_ids("a@x.com b@x.com") == ["a@x.com", "b@x.com"]


@pytest.mark.asyncio
async def test_find_existing_thread_ids_returns_empty_without_candidates():
    session = _SequentialSession([])
    result = await _find_existing_thread_ids(
        session,
        [],
        user_id="testuser",
        organization_id="org-acme",
        workspace_id="workspace-a",
    )
    assert result == {}
    assert session.execute_count == 0


@pytest.mark.asyncio
async def test_find_existing_thread_ids_dedupes_overlapping_bracket_targets():
    # A bare id and its already-bracketed form collapse to one target set, so the
    # shared "<a@x.com>" lookup key is not enqueued twice.
    session = _QueryCapturingSession([[("<a@x.com>", "thread-a")]])
    result = await _find_existing_thread_ids(
        session,
        ["<a@x.com>", "a@x.com"],
        user_id="testuser",
        organization_id="org-acme",
        workspace_id="workspace-a",
    )
    assert result == {"a@x.com": "thread-a"}


@pytest.mark.asyncio
async def test_find_existing_thread_ids_skips_rows_with_blank_thread_or_message_id():
    # A stored row with no thread_id is skipped, and a row whose message_id
    # normalizes to nothing is skipped; neither pollutes the returned map.
    session = _SequentialSession(
        [
            [
                ("<a@x.com>", None),
                ("", "thread-b"),
                ("<c@x.com>", "thread-c"),
            ]
        ]
    )
    result = await _find_existing_thread_ids(
        session,
        ["a@x.com", "c@x.com"],
        user_id="testuser",
        organization_id="org-acme",
        workspace_id="workspace-a",
    )
    assert result == {"c@x.com": "thread-c"}


@pytest.mark.asyncio
async def test_assign_thread_id_uses_a_later_candidate_when_the_first_has_no_thread():
    # The immediate parent (in_reply_to) is not yet imported, but an older
    # reference is: the lookup loop must skip the unmatched first candidate and
    # return the matched later one, not fall through to the deterministic root.
    session = _SequentialSession([[("<older@example.com>", "thread-older")]])

    thread_id = await assign_thread_id(
        session,
        {
            "message_id": "<reply@example.com>",
            "in_reply_to": "<newer@example.com>",
            "references": "<older@example.com>",
        },
        user_id="testuser",
        organization_id="org-acme",
        workspace_id="workspace-a",
    )

    assert thread_id == "thread-older"


def test_generate_email_fingerprint_is_deterministic_case_insensitive_and_field_sensitive():
    baseline = generate_email_fingerprint(
        "Quarterly plan", "Mon, 01 Jun 2026 09:00:00 +0000", "a@x.com", "b@y.com"
    )
    # 1. deterministic + SHA-256 hex digest
    assert baseline == generate_email_fingerprint(
        "Quarterly plan", "Mon, 01 Jun 2026 09:00:00 +0000", "a@x.com", "b@y.com"
    )
    assert len(baseline) == 64
    assert all(character in "0123456789abcdef" for character in baseline)
    # 2. lower-cased + outer-whitespace-stripped components collapse to one key
    assert (
        generate_email_fingerprint(
            "  QUARTERLY PLAN  ",
            "Mon, 01 Jun 2026 09:00:00 +0000",
            "A@X.com",
            "  b@Y.com ",
        )
        == baseline
    )
    # 3. None components are treated as empty (no crash) and stay distinct
    all_empty = generate_email_fingerprint(None, None, None, None)
    assert len(all_empty) == 64
    assert all_empty != baseline
    # 4. any changed component changes the fingerprint (no field is dropped)
    assert (
        generate_email_fingerprint(
            "Quarterly plan", "Mon, 01 Jun 2026 09:00:00 +0000", "a@x.com", "c@z.com"
        )
        != baseline
    )


@pytest.mark.asyncio
async def test_assign_thread_id_generates_fresh_uuid_when_no_identifiers_present():
    # An email with no in_reply_to, no references, and no message_id has nothing
    # to thread on, so a fresh uuid4 root is minted and no lookup is issued.
    session = _SequentialSession([])

    thread_id = await assign_thread_id(
        session,
        {"message_id": None, "in_reply_to": None, "references": None},
        user_id="testuser",
        organization_id="org-acme",
        workspace_id="workspace-a",
    )

    assert len(thread_id) == 32
    assert all(character in "0123456789abcdef" for character in thread_id)
    assert session.execute_count == 0


@pytest.mark.asyncio
async def test_multi_id_in_reply_to_threads_on_any_existing_parent():
    # RFC 5322 section 3.6.4: In-Reply-To is 1*msg-id, so it may carry more than
    # one parent id (a reply that joins two messages). Threading must consider
    # every parent, not treat the whole header as one opaque id -- otherwise a
    # multi-id In-Reply-To never matches an existing thread and the reply splits
    # off on its own.
    session = _SequentialSession([[("<older@example.com>", "thread-xyz")]])

    thread_id = await assign_thread_id(
        session,
        {
            "message_id": "<reply@example.com>",
            "in_reply_to": "<newer@example.com> <older@example.com>",
            "references": None,
        },
        user_id="testuser",
        organization_id="org-acme",
        workspace_id="workspace-a",
    )

    assert thread_id == "thread-xyz"


@pytest.mark.asyncio
async def test_multi_id_in_reply_to_fallback_uses_first_parent_as_root():
    session = _SequentialSession([[]])

    thread_id = await assign_thread_id(
        session,
        {
            "message_id": "<reply@example.com>",
            "in_reply_to": "<first@example.com> <second@example.com>",
            "references": None,
        },
        user_id="testuser",
        organization_id="org-acme",
        workspace_id="workspace-a",
    )

    assert thread_id == "first@example.com"


@pytest.mark.asyncio
async def test_in_reply_to_with_cfws_comment_extracts_bare_msg_id():
    # RFC 5322 sections 3.6.4 / 3.2.2 permit CFWS (e.g. a trailing comment) around
    # a msg-id. The comment text must not leak into the id, or the reply is
    # threaded/deduped against a garbage id and splits from its parent thread.
    session = _SequentialSession([[("<parent@example.com>", "thread-123")]])

    thread_id = await assign_thread_id(
        session,
        {
            "message_id": "<reply@example.com>",
            "in_reply_to": "<parent@example.com> (sent from my phone)",
            "references": None,
        },
        user_id="testuser",
        organization_id="org-acme",
        workspace_id="workspace-a",
    )

    assert thread_id == "thread-123"
