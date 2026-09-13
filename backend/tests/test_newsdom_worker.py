"""Unit tests for the NewsDOM recognition worker's per-item processing.

Fully mocked: in-memory models, an injected async config resolver, and a canned
sidecar ``request_fn`` — no database, no network. Covers the fail-closed
outcomes (unconfigured -> pending, bad payload -> failed, empty response ->
failed) that keep a pending PDF from ever masquerading as parsed.
"""

import asyncio
import base64
import datetime
from types import SimpleNamespace

import pytest

from db.models import Attachment, Document, Email
from services.content_graph import ContentSegment, ParseResult
from services.newsdom_client import NewsdomConfigurationError
from services.newsdom_pdf_recognition import (
    PDF_DOM_RECOGNITION_FAILED_STATUS,
    PDF_DOM_RECOGNITION_PENDING_STATUS,
    NewsdomRuntimeConfig,
    PdfDomRecognitionRecords,
)
import services.newsdom_worker as newsdom_worker_module

NewsdomRecognitionWorker = newsdom_worker_module.NewsdomRecognitionWorker
RESULT_FAILED = newsdom_worker_module.RESULT_FAILED
RESULT_PENDING = newsdom_worker_module.RESULT_PENDING
RESULT_RECOGNIZED = newsdom_worker_module.RESULT_RECOGNIZED
process_pending_attachment = newsdom_worker_module.process_pending_attachment
process_pending_document = newsdom_worker_module.process_pending_document


def _config() -> NewsdomRuntimeConfig:
    return NewsdomRuntimeConfig(
        base_url="https://newsdom.example.com",
        api_token=None,
        request_language="auto",
        recognition_mode="auto",
        provider_name="primary",
    )


def _canned_response() -> dict:
    return {
        "pages": [
            {
                "page_number": 1,
                "articles": [{"headline": "Headline", "body_blocks": ["Body one."]}],
            }
        ]
    }


async def _resolver_with(config):
    async def resolve(_session, _org):
        return config

    return resolve


def _pending_attachment(
    payload: bytes = b"%PDF-1.7 fake",
    *,
    attachment_id: int | None = None,
    organization_id: str = "org-1",
) -> Attachment:
    email = Email()
    email.organization_id = organization_id
    attachment = Attachment(
        id=attachment_id,
        filename="news.pdf",
        content=base64.b64encode(payload).decode("ascii"),
        parse_status=PDF_DOM_RECOGNITION_PENDING_STATUS,
    )
    email.attachments.append(attachment)
    return attachment


def _pending_document(
    document_id: str,
    *,
    organization_id: str = "org-1",
    created_at=None,
) -> Document:
    # A real, DB-flushed Document always has created_at populated (the
    # column's own default); constructing one directly, outside a session,
    # would otherwise leave it None -- an artifact of the test fixture that
    # a bare, un-flushed cursor comparison can never hit in production.
    if created_at is None:
        created_at = datetime.datetime.now(datetime.timezone.utc)
    return Document(
        document_id=document_id,
        workspace_id="ws-1",
        organization_id=organization_id,
        document_name="news.pdf",
        document_type="pdf",
        document_content=base64.b64encode(b"%PDF-1.7 fake").decode("ascii"),
        document_status=PDF_DOM_RECOGNITION_PENDING_STATUS,
        created_at=created_at,
    )


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


def _row_key(row):
    """Return the id a bulk-loaded row is keyed by for ``session.get``.

    Duck-typed (not ``isinstance``) so the expired-instance test doubles
    (``_ExpiredAttachment``/``_ExpiredDocument``, which only expose one of
    ``id``/``document_id`` and raise ``AttributeError`` on any other read)
    register under the right key without triggering that raise.
    """
    document_id = getattr(row, "document_id", None)
    return row.id if document_id is None else document_id


class _SequenceSession:
    """A fake session whose ``get`` always returns a fresh, healthy instance.

    Mirrors the real sweep contract: the bulk-loaded rows only supply ids
    and the cursor; every actual processing target is re-fetched via ``get``
    by id, exactly like a real ``AsyncSession`` would after an earlier
    item's rollback expired the bulk-loaded instances. ``by_id`` lets a
    test register a *different* object than the bulk-loaded one to prove
    that re-fetch is what the sweep actually uses.
    """

    def __init__(self, row_batches, *, by_id=None):
        self._row_batches = list(row_batches)
        self._by_id = dict(by_id or {})
        for batch in self._row_batches:
            for row in batch:
                self._by_id.setdefault(_row_key(row), row)
        self.statements = []
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        return _RowsResult(self._row_batches.pop(0))

    async def get(self, _model, row_id, options=None):
        return self._by_id.get(row_id)

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


class _AsyncSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


class _LeaseConnection:
    def __init__(self, *, scalar_result=True):
        self.scalar_result = scalar_result
        self.scalar_calls = []
        self.execution_options_calls = []
        # Ordered log spanning both call types, so a test can prove
        # AUTOCOMMIT was set BEFORE the advisory-lock query ran, not just
        # that both happened at some point.
        self.ordered_calls = []

    async def execution_options(self, **options):
        self.execution_options_calls.append(options)
        self.ordered_calls.append(("execution_options", options))
        return self

    async def scalar(self, statement, params):
        self.scalar_calls.append((statement, params))
        self.ordered_calls.append(("scalar", params))
        return self.scalar_result


class _FakeEngine:
    def __init__(self, *, dialect_name="postgresql", connection=None):
        self.dialect = SimpleNamespace(name=dialect_name)
        self._connection = connection

    def connect(self):
        return _LeaseConnectionContext(self._connection)


class _LeaseConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return False


@pytest.mark.asyncio
async def test_attachment_recognized_when_configured():
    attachment = _pending_attachment()

    async def request_fn(**_kwargs):
        return _canned_response()

    result = await process_pending_attachment(
        session=object(),
        attachment=attachment,
        config_resolver=await _resolver_with(_config()),
        request_fn=request_fn,
    )
    assert result == RESULT_RECOGNIZED
    assert attachment.parse_status == "parsed"
    assert "Headline" in attachment.content
    assert attachment.content_segments


@pytest.mark.asyncio
async def test_attachment_left_pending_when_no_provider():
    attachment = _pending_attachment()

    async def request_fn(**_kwargs):  # pragma: no cover - must not be called
        raise AssertionError("sidecar must not be called when unconfigured")

    result = await process_pending_attachment(
        session=object(),
        attachment=attachment,
        config_resolver=await _resolver_with(None),
        request_fn=request_fn,
    )
    assert result == RESULT_PENDING
    assert attachment.parse_status == PDF_DOM_RECOGNITION_PENDING_STATUS


@pytest.mark.asyncio
async def test_attachment_failed_on_invalid_payload():
    attachment = _pending_attachment()
    attachment.content = "not@@base64!!"

    async def request_fn(**_kwargs):  # pragma: no cover
        raise AssertionError("must not reach sidecar with a bad payload")

    result = await process_pending_attachment(
        session=object(),
        attachment=attachment,
        config_resolver=await _resolver_with(_config()),
        request_fn=request_fn,
    )
    assert result == RESULT_FAILED
    assert attachment.parse_status == PDF_DOM_RECOGNITION_FAILED_STATUS
    assert attachment.parse_error_code == "invalid_pending_payload"


@pytest.mark.asyncio
async def test_attachment_failed_on_empty_sidecar_response():
    attachment = _pending_attachment()

    async def request_fn(**_kwargs):
        return {"pages": []}

    result = await process_pending_attachment(
        session=object(),
        attachment=attachment,
        config_resolver=await _resolver_with(_config()),
        request_fn=request_fn,
    )
    assert result == RESULT_FAILED
    assert attachment.parse_status == PDF_DOM_RECOGNITION_FAILED_STATUS
    assert attachment.parse_error_code == "recognition_failed"
    # Never landed as parsed with empty content.
    assert attachment.parse_status != "parsed"


@pytest.mark.asyncio
async def test_attachment_orphan_and_rejected_configuration_stay_visible():
    orphan = Attachment(
        filename="orphan.pdf",
        content=base64.b64encode(b"%PDF-1.7 fake").decode("ascii"),
        parse_status=PDF_DOM_RECOGNITION_PENDING_STATUS,
    )
    orphan_result = await process_pending_attachment(
        session=object(),
        attachment=orphan,
        config_resolver=await _resolver_with(_config()),
    )
    assert orphan_result == RESULT_FAILED
    assert orphan.parse_error_code == "orphan_attachment"

    attachment = _pending_attachment()

    async def rejected_request(**_kwargs):
        raise NewsdomConfigurationError("host rejected")

    rejected_result = await process_pending_attachment(
        session=object(),
        attachment=attachment,
        config_resolver=await _resolver_with(_config()),
        request_fn=rejected_request,
    )
    assert rejected_result == RESULT_PENDING
    assert attachment.parse_status == PDF_DOM_RECOGNITION_PENDING_STATUS


@pytest.mark.asyncio
async def test_document_recognized_when_configured():
    document = Document(
        document_id="doc-1",
        workspace_id="ws-1",
        organization_id="org-1",
        document_name="news.pdf",
        document_type="pdf",
        document_content=base64.b64encode(b"%PDF-1.7 fake").decode("ascii"),
        document_status=PDF_DOM_RECOGNITION_PENDING_STATUS,
    )

    async def request_fn(**_kwargs):
        return _canned_response()

    result = await process_pending_document(
        session=object(),
        document=document,
        config_resolver=await _resolver_with(_config()),
        request_fn=request_fn,
    )
    assert result == RESULT_RECOGNIZED
    assert document.document_status == "parsed"
    assert "Headline" in document.document_content


@pytest.mark.asyncio
async def test_document_failed_on_empty_response():
    document = Document(
        document_id="doc-2",
        workspace_id="ws-1",
        organization_id="org-1",
        document_name="news.pdf",
        document_type="pdf",
        document_content=base64.b64encode(b"%PDF-1.7 fake").decode("ascii"),
        document_status=PDF_DOM_RECOGNITION_PENDING_STATUS,
    )

    async def request_fn(**_kwargs):
        return {"pages": []}

    result = await process_pending_document(
        session=object(),
        document=document,
        config_resolver=await _resolver_with(_config()),
        request_fn=request_fn,
    )
    assert result == RESULT_FAILED
    assert document.document_status == PDF_DOM_RECOGNITION_FAILED_STATUS


@pytest.mark.asyncio
async def test_document_invalid_payload_and_rejected_configuration_are_visible():
    invalid = _pending_document("doc-invalid")
    invalid.document_content = "not@@base64"
    invalid_result = await process_pending_document(
        session=object(),
        document=invalid,
        config_resolver=await _resolver_with(_config()),
    )
    assert invalid_result == RESULT_FAILED
    assert invalid.document_status == PDF_DOM_RECOGNITION_FAILED_STATUS

    document = _pending_document("doc-rejected")

    async def rejected_request(**_kwargs):
        raise NewsdomConfigurationError("host rejected")

    rejected_result = await process_pending_document(
        session=object(),
        document=document,
        config_resolver=await _resolver_with(_config()),
        request_fn=rejected_request,
    )
    assert rejected_result == RESULT_PENDING
    assert document.document_status == PDF_DOM_RECOGNITION_PENDING_STATUS


def test_attachment_mapping_keeps_unmatched_segments_without_false_parent():
    email = Email()
    attachment = Attachment(filename="news.pdf", content="pending")
    email.attachments.append(attachment)
    segment = ContentSegment(
        content_segment_uid="segment-1",
        source_kind="attachment",
        source_record_uid="attachment-1",
        content_node_uid="missing-node",
        segment_kind="paragraph",
        segment_path="/paragraph/1",
        ordinal_index=0,
        heading_path=None,
        safe_text_content="Recognized text",
        content_hash="hash",
        word_count=2,
    )
    records = PdfDomRecognitionRecords(
        parse_text="Recognized text",
        source_content_hash="source-hash",
        parse_result=ParseResult(
            source_kind="attachment",
            source_record_uid="attachment-1",
            display_name="news.pdf",
            content_type="application/pdf",
            source_content_hash="source-hash",
            nodes=(),
            segments=(segment,),
        ),
    )

    newsdom_worker_module.apply_recognition_to_attachment(
        email=email,
        attachment=attachment,
        records=records,
    )

    assert attachment.content_segments[0].content_node is None
    assert email.content_segments[0] is attachment.content_segments[0]


@pytest.mark.asyncio
async def test_attachment_sweep_advances_past_unconfigured_batch():
    blocked = [
        _pending_attachment(attachment_id=index, organization_id="org-blocked")
        for index in range(1, 11)
    ]
    ready = _pending_attachment(attachment_id=11, organization_id="org-ready")
    session = _SequenceSession([blocked, [ready]])

    async def config_resolver(_session, organization_id):
        return _config() if organization_id == "org-ready" else None

    request_count = 0

    async def request_fn(**_kwargs):
        nonlocal request_count
        request_count += 1
        return _canned_response()

    worker = NewsdomRecognitionWorker(
        batch_limit=10,
        config_resolver=config_resolver,
        request_fn=request_fn,
    )
    await worker._sweep_attachments(session)
    await worker._sweep_attachments(session)

    second_query = session.statements[1].compile()
    assert "email_attachments.id >" in str(second_query)
    assert 10 in second_query.params.values()
    assert worker._attachment_cursor == 11
    assert ready.parse_status == "parsed"
    assert request_count == 1
    assert session.commit_count == 11
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_attachment_sweep_advances_the_cursor_and_retries_the_failed_row(
    monkeypatch,
):
    # An earlier version capped the cursor at the first failure instead of
    # advancing it, to keep that row selectable later. That protected the
    # one stuck row but pinned the *whole batch window* behind it -- once
    # more than batch_limit rows were stuck at once, nothing past them was
    # ever reached (reproduced directly; see _sweep_attachments's
    # docstring). The cursor now always advances to the batch's last row;
    # the failed row is retried instead via the independent
    # _attachment_retry_ids set.
    first = _pending_attachment(attachment_id=1)
    second = _pending_attachment(attachment_id=2)
    third = _pending_attachment(attachment_id=3)
    session = _SequenceSession([[first, second, third], [second]])

    async def config_resolver(_session, _organization_id):
        return _config()

    failed_once = set()

    async def fail_the_middle_item_once(*, session, attachment, config_resolver, request_fn):
        if attachment.id == 2 and attachment.id not in failed_once:
            failed_once.add(attachment.id)
            raise RuntimeError("recognition blew up")
        return await process_pending_attachment(
            session=session,
            attachment=attachment,
            config_resolver=config_resolver,
            request_fn=request_fn,
        )

    monkeypatch.setattr(
        newsdom_worker_module, "process_pending_attachment", fail_the_middle_item_once
    )
    async def request_fn(**_kwargs):
        return _canned_response()

    worker = NewsdomRecognitionWorker(
        config_resolver=config_resolver,
        request_fn=request_fn,
    )
    await worker._sweep_attachments(session)

    assert worker._attachment_cursor == 3
    assert worker._attachment_retry_ids == {2}
    assert first.parse_status == "parsed"
    assert second.parse_status == PDF_DOM_RECOGNITION_PENDING_STATUS
    assert third.parse_status == "parsed"
    assert session.commit_count == 2
    assert session.rollback_count == 1

    # The next sweep reselects row 2 via the retry set, not the cursor
    # (which stays at 3, well past it).
    await worker._sweep_attachments(session)

    assert worker._attachment_cursor == 3
    assert worker._attachment_retry_ids == set()
    assert second.parse_status == "parsed"
    assert session.commit_count == 3


@pytest.mark.asyncio
async def test_attachment_sweep_advances_the_cursor_and_retries_the_pending_row():
    # Same fix as the failure case: RESULT_PENDING (no active provider yet)
    # no longer caps the cursor either -- it goes into _attachment_retry_ids
    # instead, so rows after it in the same batch are never held hostage.
    first = _pending_attachment(attachment_id=1, organization_id="org-unconfigured")
    second = _pending_attachment(attachment_id=2, organization_id="org-ready")
    third = _pending_attachment(attachment_id=3, organization_id="org-ready")
    session = _SequenceSession([[first, second, third], [first]])

    configured = {"org-unconfigured": False, "org-ready": True}

    async def config_resolver(_session, organization_id):
        return _config() if configured[organization_id] else None

    async def request_fn(**_kwargs):
        return _canned_response()

    worker = NewsdomRecognitionWorker(
        config_resolver=config_resolver,
        request_fn=request_fn,
    )
    await worker._sweep_attachments(session)

    assert worker._attachment_cursor == 3
    assert worker._attachment_retry_ids == {1}
    assert first.parse_status == PDF_DOM_RECOGNITION_PENDING_STATUS
    assert second.parse_status == "parsed"
    assert third.parse_status == "parsed"
    assert session.rollback_count == 0

    # Once org-unconfigured gets a provider, the retry set -- not the
    # cursor, which never revisits row 1 -- is what still reselects it.
    configured["org-unconfigured"] = True
    await worker._sweep_attachments(session)

    assert first.parse_status == "parsed"
    assert worker._attachment_retry_ids == set()


class _ExpiredAttachment:
    """Stands in for an ORM instance ``AsyncSession.rollback()`` expired.

    Any attribute read raises, exactly like touching an expired async-mapped
    instance outside an active await/greenlet context would in real
    SQLAlchemy -- proving the sweep never touches this bulk-loaded object
    for its *own* processing once it has already failed and been rolled
    back once.
    """

    id = 1

    def __getattr__(self, _name):
        raise AttributeError(
            "must not read attributes off the stale bulk-loaded instance"
        )


class _ExpiredDocument:
    """Document counterpart of ``_ExpiredAttachment``."""

    document_id = "doc-001"

    def __getattr__(self, _name):
        raise AttributeError(
            "must not read attributes off the stale bulk-loaded instance"
        )


@pytest.mark.asyncio
async def test_attachment_sweep_never_processes_the_bulk_loaded_instance_directly():
    poisoned_first = _ExpiredAttachment()
    fresh_first = _pending_attachment(attachment_id=1, organization_id="org-ready")
    second = _pending_attachment(attachment_id=2, organization_id="org-ready")
    # The bulk query "sees" the poisoned stand-in for id 1 (as a real
    # AsyncSession would after some earlier rollback expired it), but `get`
    # returns the real, healthy row -- proving the sweep re-fetches instead
    # of processing the bulk-loaded object directly.
    session = _SequenceSession(
        [[poisoned_first, second]], by_id={1: fresh_first, 2: second}
    )

    async def config_resolver(_session, _organization_id):
        return _config()

    async def request_fn(**_kwargs):
        return _canned_response()

    worker = NewsdomRecognitionWorker(
        config_resolver=config_resolver, request_fn=request_fn
    )
    await worker._sweep_attachments(session)

    assert fresh_first.parse_status == "parsed"
    assert second.parse_status == "parsed"
    assert session.commit_count == 2
    assert session.rollback_count == 0


class _LivePendingAttachmentSession:
    """A session whose pending-attachment query genuinely reflects the
    worker's own (cursor, retry_ids) filtering, instead of replaying a
    pre-scripted sequence of batches like ``_SequenceSession``.

    ``_SequenceSession`` is fine for single-sweep, single-assertion tests,
    but it can't prove a *multi-sweep scheduling* claim: it would happily
    "return" whatever batch a test pre-registers regardless of whether the
    real query would ever actually produce it. Reproducing the Devin-review
    finding this fixes (more than ``batch_limit`` consecutive permanently-
    pending rows starve every row after them) needs a fake that mirrors
    what a real database would return for
    ``NewsdomRecognitionWorker._pending_attachment_statement`` across many
    sweeps: every attachment still carrying
    ``PDF_DOM_RECOGNITION_PENDING_STATUS`` whose id is either past the
    worker's forward cursor or in its retry set, forward rows ordered ahead
    of retry rows, capped at ``batch_limit``.
    """

    def __init__(self, worker, attachments):
        self._worker = worker
        self._table = {attachment.id: attachment for attachment in attachments}
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, _statement):
        cursor = self._worker._attachment_cursor
        retry_ids = self._worker._attachment_retry_ids
        pending = [
            row
            for row in self._table.values()
            if row.parse_status == PDF_DOM_RECOGNITION_PENDING_STATUS
            and (cursor is None or row.id > cursor or row.id in retry_ids)
        ]
        pending.sort(key=lambda row: (0 if (cursor is None or row.id > cursor) else 1, row.id))
        return _RowsResult(pending[: self._worker.batch_limit])

    async def get(self, _model, row_id, options=None):
        return self._table.get(row_id)

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


@pytest.mark.asyncio
async def test_attachment_sweep_does_not_starve_rows_behind_many_stuck_rows():
    # The Devin-review finding this fixes: an organization bulk-imports a
    # burst of PDFs before ever configuring a provider -- more than
    # batch_limit consecutive rows land pending at once. Reproduced first
    # against the pre-fix code (cursor capped at the first unresolved row):
    # with 60 leading stuck rows and batch_limit=50, every sweep re-selected
    # the same first 50 stuck rows forever and the 60 healthy rows behind
    # them were never reached, even after 14 sweeps.
    blocked = [
        _pending_attachment(attachment_id=index, organization_id="org-blocked")
        for index in range(1, 61)
    ]
    ready = [
        _pending_attachment(attachment_id=index, organization_id="org-ready")
        for index in range(61, 121)
    ]
    all_attachments = blocked + ready

    async def config_resolver(_session, organization_id):
        return _config() if organization_id == "org-ready" else None

    async def request_fn(**_kwargs):
        return _canned_response()

    worker = NewsdomRecognitionWorker(
        batch_limit=50, config_resolver=config_resolver, request_fn=request_fn
    )
    session = _LivePendingAttachmentSession(worker, all_attachments)

    for _ in range(10):
        await worker._sweep_attachments(session)
        if all(a.parse_status == "parsed" for a in ready):
            break

    assert all(a.parse_status == "parsed" for a in ready)
    assert all(
        a.parse_status == PDF_DOM_RECOGNITION_PENDING_STATUS for a in blocked
    )
    assert worker._attachment_retry_ids == {a.id for a in blocked}


@pytest.mark.asyncio
async def test_attachment_sweep_rediscovers_a_row_reverted_to_pending_behind_the_cursor():
    # An already-recognized attachment can, in principle, be explicitly
    # re-marked pending again later (the same class of external transition
    # Devin Review flagged for the reparse worker's reparse-intent endpoint,
    # and for documents' pdf-dom-recognition-intent endpoint) -- its id is
    # then already behind the forward cursor, and it was never seen as
    # unresolved so it isn't in the retry set either. A periodic full
    # rescan (every FULL_RESCAN_EVERY_N_SWEEPS sweeps) bounds how long such
    # a row can stay invisible.
    reverted = _pending_attachment(attachment_id=1, organization_id="org-ready")

    async def config_resolver(_session, _organization_id):
        return _config()

    async def request_fn(**_kwargs):
        return _canned_response()

    worker = NewsdomRecognitionWorker(
        config_resolver=config_resolver, request_fn=request_fn
    )
    session = _LivePendingAttachmentSession(worker, [reverted])

    await worker._sweep_attachments(session)
    assert reverted.parse_status == "parsed"
    assert worker._attachment_cursor == 1

    reverted.parse_status = PDF_DOM_RECOGNITION_PENDING_STATUS

    rediscovered_at = None
    for sweep_number in range(2, newsdom_worker_module.FULL_RESCAN_EVERY_N_SWEEPS + 1):
        await worker._sweep_attachments(session)
        if reverted.parse_status != PDF_DOM_RECOGNITION_PENDING_STATUS:
            rediscovered_at = sweep_number
            break

    assert rediscovered_at == newsdom_worker_module.FULL_RESCAN_EVERY_N_SWEEPS


class _LivePendingDocumentSession:
    """Document counterpart of ``_LivePendingAttachmentSession`` -- mirrors
    ``NewsdomRecognitionWorker._pending_document_statement`` for real,
    including its ``(created_at, document_id)`` forward comparison, so a
    test can prove the query genuinely reaches a document whose random UUID
    sorts below the cursor but whose ``created_at`` sorts after it.
    """

    def __init__(self, worker, documents):
        self._worker = worker
        self._table = {document.document_id: document for document in documents}
        self.commit_count = 0
        self.rollback_count = 0

    def _is_forward(self, document):
        cursor = self._worker._document_cursor
        if cursor is None:
            return True
        cursor_created_at, cursor_document_id = cursor
        if document.created_at != cursor_created_at:
            return document.created_at > cursor_created_at
        return document.document_id > cursor_document_id

    async def execute(self, _statement):
        retry_ids = self._worker._document_retry_ids
        pending = [
            row
            for row in self._table.values()
            if row.document_status == PDF_DOM_RECOGNITION_PENDING_STATUS
            and (self._is_forward(row) or row.document_id in retry_ids)
        ]
        pending.sort(
            key=lambda row: (
                0 if self._is_forward(row) else 1,
                row.created_at,
                row.document_id,
            )
        )
        return _RowsResult(pending[: self._worker.batch_limit])

    async def get(self, _model, document_id):
        return self._table.get(document_id)

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


@pytest.mark.asyncio
async def test_document_sweep_cursor_uses_created_at_not_document_id_ordering():
    # Document.document_id defaults to a random UUID (db/models.py: default=
    # lambda: f"doc_{uuid.uuid4().hex}"), so it is NOT monotonic with
    # insertion order -- a document inserted later can sort lexicographically
    # *below* one inserted earlier. Devin Review flagged that a cursor based
    # on document_id alone would then permanently miss such a row: it is
    # never in the retry set (never seen before) and never satisfies
    # "document_id > cursor" (it sorts lower), so it would stay pending
    # forever. The cursor is now a (created_at, document_id) tuple --
    # created_at is genuinely monotonic with insertion order.
    early = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    later = datetime.datetime(2026, 1, 2, tzinfo=datetime.timezone.utc)
    # "doc-zzz" sorts after "doc-aaa" as a string, despite being created
    # first -- exactly the adversarial ordering the fix must survive.
    already_seen = _pending_document(
        "doc-zzz", organization_id="org-ready", created_at=early
    )
    new_arrival = _pending_document(
        "doc-aaa", organization_id="org-ready", created_at=later
    )

    async def config_resolver(_session, _organization_id):
        return _config()

    async def request_fn(**_kwargs):
        return _canned_response()

    worker = NewsdomRecognitionWorker(
        config_resolver=config_resolver, request_fn=request_fn
    )
    session = _LivePendingDocumentSession(worker, [already_seen])
    await worker._sweep_documents(session)
    assert worker._document_cursor == (early, "doc-zzz")
    assert already_seen.document_status == "parsed"

    # The new, later-arriving document lands in the same table only once it
    # actually exists -- exactly like a real insert between sweeps.
    session._table["doc-aaa"] = new_arrival
    await worker._sweep_documents(session)

    assert new_arrival.document_status == "parsed"


@pytest.mark.asyncio
async def test_document_sweep_rediscovers_a_row_reverted_to_pending_behind_the_cursor():
    # POST .../pdf-dom-recognition-intent (backend/api/data.py) can
    # explicitly re-trigger recognition on ANY existing document, including
    # one whose (created_at, document_id) is already behind the forward
    # cursor. Neither the cursor nor the retry set can discover that on its
    # own; a periodic full rescan bounds how long it can stay invisible.
    reverted = _pending_document("doc-001", organization_id="org-ready")

    async def config_resolver(_session, _organization_id):
        return _config()

    async def request_fn(**_kwargs):
        return _canned_response()

    worker = NewsdomRecognitionWorker(
        config_resolver=config_resolver, request_fn=request_fn
    )
    session = _LivePendingDocumentSession(worker, [reverted])

    await worker._sweep_documents(session)
    assert reverted.document_status == "parsed"
    cursor_after_first_sweep = worker._document_cursor

    # Simulate an operator re-triggering recognition on this now-old
    # document -- its (created_at, document_id) is already behind the cursor.
    reverted.document_status = PDF_DOM_RECOGNITION_PENDING_STATUS

    rediscovered_at = None
    for sweep_number in range(2, newsdom_worker_module.FULL_RESCAN_EVERY_N_SWEEPS + 1):
        await worker._sweep_documents(session)
        if reverted.document_status != PDF_DOM_RECOGNITION_PENDING_STATUS:
            rediscovered_at = sweep_number
            break

    assert rediscovered_at == newsdom_worker_module.FULL_RESCAN_EVERY_N_SWEEPS
    assert cursor_after_first_sweep == (reverted.created_at, "doc-001")


@pytest.mark.asyncio
async def test_document_sweep_advances_the_cursor_and_retries_a_blocked_row():
    # A batch that fully resolves lets the cursor advance to its tail (a
    # lexicographic max, since document_id is a string). A later-arriving
    # row that's still blocked (no provider configured for its org) goes
    # into _document_retry_ids instead of relying on the query going empty
    # to trigger a full rescan -- an earlier design's wrap-to-None never
    # fired under continuous inbound traffic (new rows keep landing past
    # the cursor, so the query never returns zero rows), which could starve
    # that row forever. See _sweep_attachments's docstring for the fuller
    # rationale (identical fix, shared between both sweeps).
    resolved_batch = [
        _pending_document(f"doc-{index:03d}", organization_id="org-ready")
        for index in range(1, 11)
    ]
    late_arrival = _pending_document("doc-011", organization_id="org-blocked")
    # The re-sweep re-fetches "doc-011" by id -- exactly like a real
    # database would return the current state of that single row, not a
    # separate instance -- so simulate "it became configured" by mutating
    # the same object rather than registering a second, distinct Document
    # under the same id.
    session = _SequenceSession([resolved_batch, [late_arrival], [late_arrival]])

    async def config_resolver(_session, organization_id):
        return _config() if organization_id == "org-ready" else None

    async def request_fn(**_kwargs):
        return _canned_response()

    worker = NewsdomRecognitionWorker(
        batch_limit=10,
        config_resolver=config_resolver,
        request_fn=request_fn,
    )
    await worker._sweep_documents(session)
    assert worker._document_cursor == (resolved_batch[-1].created_at, "doc-010")
    assert worker._document_retry_ids == set()
    for document in resolved_batch:
        assert document.document_status == "parsed"

    await worker._sweep_documents(session)
    # The cursor still advances (to doc-011, past doc-010), but doc-011
    # stays pending and now enters the retry set rather than forcing a
    # rescan-from-scratch.
    assert worker._document_cursor == (late_arrival.created_at, "doc-011")
    assert worker._document_retry_ids == {"doc-011"}
    assert late_arrival.document_status == PDF_DOM_RECOGNITION_PENDING_STATUS

    late_arrival.organization_id = "org-ready"
    await worker._sweep_documents(session)
    assert worker._document_cursor == (late_arrival.created_at, "doc-011")
    assert worker._document_retry_ids == set()
    assert late_arrival.document_status == "parsed"

    assert session.commit_count == 12
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_document_sweep_advances_the_cursor_and_retries_the_failed_row(
    monkeypatch,
):
    # Same fix as the attachment sweep, adapted for the string-keyed
    # document cursor: the cursor always advances to the batch's last row
    # (a lexicographic max) instead of capping at the first failure, and the
    # failed row is retried via _document_retry_ids instead.
    first = _pending_document("doc-001")
    second = _pending_document("doc-002")
    third = _pending_document("doc-003")
    session = _SequenceSession([[first, second, third], [second]])

    async def config_resolver(_session, _organization_id):
        return _config()

    failed_once = set()

    async def fail_the_middle_item_once(*, session, document, config_resolver, request_fn):
        if document.document_id == "doc-002" and document.document_id not in failed_once:
            failed_once.add(document.document_id)
            raise RuntimeError("recognition blew up")
        return await process_pending_document(
            session=session,
            document=document,
            config_resolver=config_resolver,
            request_fn=request_fn,
        )

    monkeypatch.setattr(
        newsdom_worker_module, "process_pending_document", fail_the_middle_item_once
    )
    async def request_fn(**_kwargs):
        return _canned_response()

    worker = NewsdomRecognitionWorker(
        config_resolver=config_resolver,
        request_fn=request_fn,
    )
    await worker._sweep_documents(session)

    assert worker._document_cursor == (third.created_at, "doc-003")
    assert worker._document_retry_ids == {"doc-002"}
    assert first.document_status == "parsed"
    assert second.document_status == PDF_DOM_RECOGNITION_PENDING_STATUS
    assert third.document_status == "parsed"
    assert session.commit_count == 2
    assert session.rollback_count == 1

    await worker._sweep_documents(session)

    assert worker._document_cursor == (third.created_at, "doc-003")
    assert worker._document_retry_ids == set()
    assert second.document_status == "parsed"
    assert session.commit_count == 3


@pytest.mark.asyncio
async def test_document_sweep_advances_the_cursor_and_retries_the_pending_row():
    # Same fix as the attachment sweep: RESULT_PENDING no longer caps the
    # cursor either -- it goes into _document_retry_ids instead.
    first = _pending_document("doc-001", organization_id="org-unconfigured")
    second = _pending_document("doc-002", organization_id="org-ready")
    third = _pending_document("doc-003", organization_id="org-ready")
    session = _SequenceSession([[first, second, third], [first]])

    configured = {"org-unconfigured": False, "org-ready": True}

    async def config_resolver(_session, organization_id):
        return _config() if configured[organization_id] else None

    async def request_fn(**_kwargs):
        return _canned_response()

    worker = NewsdomRecognitionWorker(
        config_resolver=config_resolver,
        request_fn=request_fn,
    )
    await worker._sweep_documents(session)

    assert worker._document_cursor == (third.created_at, "doc-003")
    assert worker._document_retry_ids == {"doc-001"}
    assert first.document_status == PDF_DOM_RECOGNITION_PENDING_STATUS
    assert second.document_status == "parsed"
    assert third.document_status == "parsed"
    assert session.rollback_count == 0

    configured["org-unconfigured"] = True
    await worker._sweep_documents(session)

    assert first.document_status == "parsed"
    assert worker._document_retry_ids == set()


@pytest.mark.asyncio
async def test_document_sweep_never_processes_the_bulk_loaded_instance_directly():
    poisoned_first = _ExpiredDocument()
    fresh_first = _pending_document("doc-001", organization_id="org-ready")
    second = _pending_document("doc-002", organization_id="org-ready")
    session = _SequenceSession(
        [[poisoned_first, second]],
        by_id={"doc-001": fresh_first, "doc-002": second},
    )

    async def config_resolver(_session, _organization_id):
        return _config()

    async def request_fn(**_kwargs):
        return _canned_response()

    worker = NewsdomRecognitionWorker(
        config_resolver=config_resolver, request_fn=request_fn
    )
    await worker._sweep_documents(session)

    assert fresh_first.document_status == "parsed"
    assert second.document_status == "parsed"
    assert session.commit_count == 2
    assert session.rollback_count == 0


@pytest.mark.asyncio
async def test_load_pending_attachments_queries_forward_cursor_and_retry_ids():
    # No more wraparound: a persistently-stuck row is retried via an
    # explicit "id IN retry_ids" filter, independent of the forward cursor,
    # instead of relying on the query going empty to trigger a rescan (which
    # never happens once new rows keep landing past the cursor).
    row = _pending_attachment(attachment_id=5)
    session = _SequenceSession([[row]])
    worker = NewsdomRecognitionWorker(batch_limit=10)
    worker._attachment_cursor = 3
    worker._attachment_retry_ids = {1}

    rows = await worker._load_pending_attachments(session)

    assert rows == [row]
    compiled = str(session.statements[0].compile())
    assert "email_attachments.id >" in compiled
    assert "IN" in compiled.upper()


@pytest.mark.asyncio
async def test_load_pending_attachments_has_no_id_filter_before_the_first_sweep():
    row = _pending_attachment(attachment_id=1)
    session = _SequenceSession([[row]])
    worker = NewsdomRecognitionWorker(batch_limit=10)

    rows = await worker._load_pending_attachments(session)

    assert rows == [row]
    compiled = str(session.statements[0].compile())
    assert "email_attachments.id >" not in compiled
    assert "IN" not in compiled.upper()


@pytest.mark.asyncio
async def test_empty_sweeps_leave_both_cursors_unset():
    attachment_session = _SequenceSession([[]])
    document_session = _SequenceSession([[]])
    worker = NewsdomRecognitionWorker()

    await worker._sweep_attachments(attachment_session)
    await worker._sweep_documents(document_session)

    assert worker._attachment_cursor is None
    assert worker._document_cursor is None
    assert attachment_session.commit_count == 0
    assert document_session.commit_count == 0


@pytest.mark.asyncio
async def test_sweeps_rollback_one_item_failure_and_continue_isolation():
    attachment = _pending_attachment(attachment_id=1)
    document = _pending_document("doc-1")
    attachment_session = _SequenceSession([[attachment]])
    document_session = _SequenceSession([[document]])

    async def broken_resolver(_session, _organization_id):
        raise RuntimeError("provider lookup failed")

    worker = NewsdomRecognitionWorker(config_resolver=broken_resolver)
    await worker._sweep_attachments(attachment_session)
    await worker._sweep_documents(document_session)

    assert attachment_session.commit_count == 0
    assert attachment_session.rollback_count == 1
    assert document_session.commit_count == 0
    assert document_session.rollback_count == 1


@pytest.mark.asyncio
async def test_postgresql_lease_helpers_and_non_postgresql_fallback(monkeypatch):
    postgres_connection = _LeaseConnection(scalar_result=1)

    assert (
        await newsdom_worker_module._try_acquire_sweep_lease(postgres_connection)
        is True
    )
    # AUTOCOMMIT before the lock-acquire statement: a plain (non-autocommit)
    # connection would otherwise leave this connection's implicit
    # transaction open and idle for the whole sweep -- a PostgreSQL
    # idle_in_transaction_session_timeout could then kill this connection
    # mid-sweep, silently dropping the lease.
    assert postgres_connection.execution_options_calls == [
        {"isolation_level": "AUTOCOMMIT"}
    ]
    assert (
        postgres_connection.scalar_calls[0][1]
        == newsdom_worker_module._SWEEP_LOCK_PARAMS
    )
    # Ordering, not just occurrence: AUTOCOMMIT must be set before the
    # advisory-lock query runs, or the query could still open an implicit
    # transaction under the connection's prior isolation level.
    assert postgres_connection.ordered_calls[0][0] == "execution_options"
    assert postgres_connection.ordered_calls[1][0] == "scalar"
    await newsdom_worker_module._release_sweep_lease(postgres_connection)
    assert len(postgres_connection.scalar_calls) == 2

    monkeypatch.setattr(
        newsdom_worker_module, "engine", _FakeEngine(dialect_name="sqlite")
    )
    assert newsdom_worker_module._engine_uses_postgresql() is False

    monkeypatch.setattr(
        newsdom_worker_module, "engine", _FakeEngine(dialect_name="postgresql")
    )
    assert newsdom_worker_module._engine_uses_postgresql() is True


@pytest.mark.asyncio
async def test_worker_sweep_skips_locking_when_engine_is_not_postgresql(monkeypatch):
    session = object()
    calls = []
    worker = NewsdomRecognitionWorker()

    monkeypatch.setattr(
        newsdom_worker_module, "engine", _FakeEngine(dialect_name="sqlite")
    )
    monkeypatch.setattr(
        newsdom_worker_module,
        "AsyncSessionLocal",
        lambda: _AsyncSessionContext(session),
    )

    async def sweep_attachments(actual_session):
        calls.append(("attachments", actual_session))

    async def sweep_documents(actual_session):
        calls.append(("documents", actual_session))

    monkeypatch.setattr(worker, "_sweep_attachments", sweep_attachments)
    monkeypatch.setattr(worker, "_sweep_documents", sweep_documents)

    await worker._sweep()

    assert calls == [("attachments", session), ("documents", session)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("lease", "expected_sweeps", "expected_releases"),
    [(False, 0, 0), (True, 2, 1)],
)
async def test_worker_sweep_honors_lease_outcome(
    monkeypatch, lease, expected_sweeps, expected_releases
):
    session = object()
    lock_connection = object()
    calls = []
    releases = []
    worker = NewsdomRecognitionWorker()

    monkeypatch.setattr(
        newsdom_worker_module,
        "engine",
        _FakeEngine(dialect_name="postgresql", connection=lock_connection),
    )
    monkeypatch.setattr(
        newsdom_worker_module,
        "AsyncSessionLocal",
        lambda: _AsyncSessionContext(session),
    )

    async def acquire(actual_connection):
        assert actual_connection is lock_connection
        return lease

    async def release(actual_connection):
        releases.append(actual_connection)

    async def sweep_attachments(actual_session):
        calls.append(("attachments", actual_session))

    async def sweep_documents(actual_session):
        calls.append(("documents", actual_session))

    monkeypatch.setattr(newsdom_worker_module, "_try_acquire_sweep_lease", acquire)
    monkeypatch.setattr(newsdom_worker_module, "_release_sweep_lease", release)
    monkeypatch.setattr(worker, "_sweep_attachments", sweep_attachments)
    monkeypatch.setattr(worker, "_sweep_documents", sweep_documents)

    await worker._sweep()

    assert len(calls) == expected_sweeps
    assert len(releases) == expected_releases


@pytest.mark.asyncio
async def test_worker_start_stop_are_idempotent(monkeypatch):
    worker = NewsdomRecognitionWorker()
    entered = asyncio.Event()
    blocker = asyncio.Event()

    async def blocked_loop():
        entered.set()
        await blocker.wait()

    monkeypatch.setattr(worker, "_run_loop", blocked_loop)
    await worker.start()
    await entered.wait()
    task = worker._task
    await worker.start()
    await worker.stop()
    await worker.stop()

    assert task is not None
    assert task.cancelled()

    worker._is_running = True
    worker._task = None
    await worker.stop()


@pytest.mark.asyncio
async def test_worker_loop_reports_errors_and_honors_cancellation(monkeypatch):
    worker = NewsdomRecognitionWorker(interval_seconds=1)
    worker._is_running = True
    sleep_calls = 0

    async def sleep_then_cancel(_seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls > 1:
            raise asyncio.CancelledError

    async def failing_sweep():
        raise RuntimeError("sweep failed")

    monkeypatch.setattr(newsdom_worker_module.asyncio, "sleep", sleep_then_cancel)
    monkeypatch.setattr(worker, "_sweep", failing_sweep)
    await worker._run_loop()
    assert sleep_calls == 2

    async def cancel_immediately(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(newsdom_worker_module.asyncio, "sleep", cancel_immediately)
    await worker._run_loop()


@pytest.mark.asyncio
async def test_worker_loop_stops_when_sweep_is_cancelled(monkeypatch):
    worker = NewsdomRecognitionWorker(interval_seconds=1)
    worker._is_running = True

    async def no_sleep(_seconds):
        return None

    async def cancelled_sweep():
        raise asyncio.CancelledError

    monkeypatch.setattr(newsdom_worker_module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(worker, "_sweep", cancelled_sweep)
    await worker._run_loop()


@pytest.mark.asyncio
async def test_worker_loop_returns_after_a_normal_interval(monkeypatch):
    worker = NewsdomRecognitionWorker(interval_seconds=1)
    worker._is_running = True
    sleep_calls = 0
    sweep_calls = 0

    async def stop_after_interval(_seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 2:
            worker._is_running = False

    async def successful_sweep():
        nonlocal sweep_calls
        sweep_calls += 1

    monkeypatch.setattr(newsdom_worker_module.asyncio, "sleep", stop_after_interval)
    monkeypatch.setattr(worker, "_sweep", successful_sweep)
    await worker._run_loop()

    assert sleep_calls == 2
    assert sweep_calls == 1


@pytest.mark.asyncio
async def test_worker_loop_skips_interval_when_sweep_stops_worker(monkeypatch):
    worker = NewsdomRecognitionWorker(interval_seconds=1)
    worker._is_running = True
    sleep_calls = 0

    async def record_sleep(_seconds):
        nonlocal sleep_calls
        sleep_calls += 1

    async def stopping_sweep():
        worker._is_running = False

    monkeypatch.setattr(newsdom_worker_module.asyncio, "sleep", record_sleep)
    monkeypatch.setattr(worker, "_sweep", stopping_sweep)
    await worker._run_loop()

    assert sleep_calls == 1
