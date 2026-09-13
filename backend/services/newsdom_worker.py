"""Background worker glue for NewsDOM PDF DOM recognition.

Attachments and workspace documents whose PDF recognition was deferred at
import time are processed here: the sidecar is called (via
:mod:`services.newsdom_pdf_recognition`) and the returned tree is landed into
the persisted attachment/document content and, for attachments, the
``content_nodes`` / ``content_segments`` graph.

The apply functions are deliberately session-free so they can be unit tested
with in-memory model instances and a mocked NewsDOM client.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import random
from collections.abc import Awaitable, Callable

from sqlalchemy import and_, bindparam, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from sqlalchemy.orm import selectinload

from db.models import (
    Attachment,
    ContentNodeRecord,
    ContentSegmentRecord,
    Document,
    Email,
)
from db.session import AsyncSessionLocal, engine
from services.attachment_parser import decode_deferred_attachment_payload
from services.content_graph import ParseResult
from services.newsdom_client import (
    NewsdomConfigurationError,
    NewsdomRequestError,
    request_pdf_dom,
)
from services.newsdom_pdf_recognition import (
    PDF_DOM_RECOGNITION_FAILED_STATUS,
    PDF_DOM_RECOGNITION_PARSED_STATUS,
    PDF_DOM_RECOGNITION_PENDING_STATUS,
    PDF_PARSE_CONTENT_TYPE,
    PDF_PARSER_KEY,
    NewsdomRuntimeConfig,
    ParseRequestFn,
    PdfDomRecognitionRecords,
    recognize_pdf_dom,
    resolve_newsdom_config_from_db,
)

logger = logging.getLogger(__name__)
_sysrand = random.SystemRandom()

# How the worker resolves a runtime config for an organization. Injectable so
# the per-item processors are unit-testable without a database.
ConfigResolver = Callable[
    [AsyncSession, str | None], Awaitable[NewsdomRuntimeConfig | None]
]


def _append_parse_result_to_attachment(
    *,
    email: Email,
    attachment: Attachment,
    parse_result: ParseResult,
) -> None:
    """Append recognized graph records to an email and its attachment."""
    node_records_by_uid: dict[str, ContentNodeRecord] = {}
    for parsed_node in parse_result.nodes:
        node_record = ContentNodeRecord(
            content_node_uid=parsed_node.content_node_uid,
            source_kind=parsed_node.source_kind,
            source_record_uid=parsed_node.source_record_uid,
            parent_node_uid=parsed_node.parent_node_uid,
            node_kind=parsed_node.node_kind,
            node_path=parsed_node.node_path,
            ordinal_index=parsed_node.ordinal_index,
            display_label=parsed_node.display_label,
            safe_text_content=parsed_node.safe_text_content,
            content_hash=parsed_node.content_hash,
        )
        email.content_nodes.append(node_record)
        attachment.content_nodes.append(node_record)
        node_records_by_uid[parsed_node.content_node_uid] = node_record

    for parsed_segment in parse_result.segments:
        node_record = node_records_by_uid.get(parsed_segment.content_node_uid)
        segment_record = ContentSegmentRecord(
            content_segment_uid=parsed_segment.content_segment_uid,
            source_kind=parsed_segment.source_kind,
            source_record_uid=parsed_segment.source_record_uid,
            segment_kind=parsed_segment.segment_kind,
            segment_path=parsed_segment.segment_path,
            ordinal_index=parsed_segment.ordinal_index,
            heading_path=parsed_segment.heading_path,
            safe_text_content=parsed_segment.safe_text_content,
            content_hash=parsed_segment.content_hash,
            word_count=parsed_segment.word_count,
        )
        if node_record is not None:
            node_record.segments.append(segment_record)
        email.content_segments.append(segment_record)
        attachment.content_segments.append(segment_record)


def apply_recognition_to_attachment(
    *,
    email: Email,
    attachment: Attachment,
    records: PdfDomRecognitionRecords,
) -> None:
    """Land recognized PDF DOM records onto an attachment (text + graph)."""
    attachment.content = records.parse_text
    attachment.parse_content_type = PDF_PARSE_CONTENT_TYPE
    attachment.parser_key = PDF_PARSER_KEY
    attachment.parse_status = PDF_DOM_RECOGNITION_PARSED_STATUS
    attachment.parse_error_code = None
    _append_parse_result_to_attachment(
        email=email,
        attachment=attachment,
        parse_result=records.parse_result,
    )


def apply_recognition_to_document(
    *,
    document: Document,
    records: PdfDomRecognitionRecords,
) -> None:
    """Land recognized PDF text onto a workspace document (mirrors the HWP
    conversion worker: content + status, no content graph rows)."""
    document.document_content = records.parse_text
    document.document_status = PDF_DOM_RECOGNITION_PARSED_STATUS


async def recognize_attachment_pdf(
    *,
    email: Email,
    attachment: Attachment,
    pdf_bytes: bytes,
    config: NewsdomRuntimeConfig | None,
    source_record_uid: str,
    request_fn: ParseRequestFn = request_pdf_dom,
) -> PdfDomRecognitionRecords:
    """Recognize a PDF and land its text and graph on an attachment."""
    records = await recognize_pdf_dom(
        config=config,
        pdf_bytes=pdf_bytes,
        filename=attachment.filename or "attachment.pdf",
        source_kind="attachment",
        source_record_uid=source_record_uid,
        display_name=attachment.filename or "",
        request_fn=request_fn,
    )
    apply_recognition_to_attachment(email=email, attachment=attachment, records=records)
    return records


async def recognize_document_pdf(
    *,
    document: Document,
    pdf_bytes: bytes,
    config: NewsdomRuntimeConfig | None,
    request_fn: ParseRequestFn = request_pdf_dom,
) -> PdfDomRecognitionRecords:
    """Recognize a PDF and land its text on a workspace document."""
    records = await recognize_pdf_dom(
        config=config,
        pdf_bytes=pdf_bytes,
        filename=document.document_name or "document.pdf",
        source_kind="workspace_document",
        source_record_uid=document.document_id,
        display_name=document.document_name or "",
        request_fn=request_fn,
    )
    apply_recognition_to_document(document=document, records=records)
    return records


# --------------------------------------------------------------------------
# Production worker: sweep pending attachments/documents and recognize them.
# --------------------------------------------------------------------------

DEFAULT_NEWSDOM_INTERVAL_SECONDS = 60
DEFAULT_NEWSDOM_BATCH_LIMIT = 10
NEWSDOM_SWEEP_LOCK_NAMESPACE = "naruon-newsdom-recognition-sweep"
MAX_STARTUP_JITTER_SECONDS = 30
# A row already past the forward cursor can still be explicitly re-marked
# pending later (e.g. POST .../pdf-dom-recognition-intent re-triggering an
# already-resolved document) -- the cursor+retry-id design alone can never
# discover that, since retry_ids only tracks rows this worker itself has
# already seen and found unresolved. Forcing a full rescan (cursor -> None)
# on this cadence bounds how stale such a row can get; it's always safe
# regardless of cadence, since the parse_status/document_status filter
# already excludes every row that's actually resolved, so a full rescan
# only ever costs a wider (not wrong) result set. See _sweep_attachments.
FULL_RESCAN_EVERY_N_SWEEPS = 20

# Per-item processing outcomes.
RESULT_RECOGNIZED = "recognized"
RESULT_PENDING = "pending"
RESULT_FAILED = "failed"

_SWEEP_LOCK_PARAMS = {
    "namespace_key": NEWSDOM_SWEEP_LOCK_NAMESPACE,
    "sweep_key": "sweep",
}


async def process_pending_attachment(
    *,
    session: AsyncSession,
    attachment: Attachment,
    config_resolver: ConfigResolver = resolve_newsdom_config_from_db,
    request_fn: ParseRequestFn = request_pdf_dom,
) -> str:
    """Recognize one pending attachment PDF, or record a safe outcome.

    Returns ``RESULT_RECOGNIZED`` on success, ``RESULT_PENDING`` when no active
    provider is configured yet (left pending to retry later), or
    ``RESULT_FAILED`` when the payload or the sidecar response is unusable (a
    visible failure status is recorded - never a false ``parsed``).
    """
    email = attachment.email
    if email is None:
        attachment.parse_status = PDF_DOM_RECOGNITION_FAILED_STATUS
        attachment.parse_error_code = "orphan_attachment"
        return RESULT_FAILED
    try:
        pdf_bytes = decode_deferred_attachment_payload(attachment.content)
    except ValueError as exc:
        attachment.parse_status = PDF_DOM_RECOGNITION_FAILED_STATUS
        attachment.parse_error_code = "invalid_pending_payload"
        logger.warning(
            "NewsDOM attachment %s rejected before recognition: %s",
            getattr(attachment, "id", "?"),
            exc,
        )
        return RESULT_FAILED

    config = await config_resolver(session, email.organization_id)
    if config is None:
        # Degrade gracefully: no active NewsDOM provider for this org yet.
        logger.info(
            "NewsDOM attachment %s remains pending: no active provider for "
            "organization %s.",
            getattr(attachment, "id", "?"),
            email.organization_id or "personal-scope",
        )
        return RESULT_PENDING

    try:
        await recognize_attachment_pdf(
            email=email,
            attachment=attachment,
            pdf_bytes=pdf_bytes,
            config=config,
            source_record_uid=f"attachment-{attachment.id}",
            request_fn=request_fn,
        )
    except NewsdomConfigurationError as exc:
        logger.warning(
            "NewsDOM attachment %s remains pending: provider configuration "
            "was rejected: %s",
            getattr(attachment, "id", "?"),
            exc,
        )
        return RESULT_PENDING
    except (NewsdomRequestError, ValueError) as exc:
        attachment.parse_status = PDF_DOM_RECOGNITION_FAILED_STATUS
        attachment.parse_error_code = "recognition_failed"
        logger.warning(
            "NewsDOM attachment %s recognition failed: %s",
            getattr(attachment, "id", "?"),
            exc,
        )
        return RESULT_FAILED
    return RESULT_RECOGNIZED


async def process_pending_document(
    *,
    session: AsyncSession,
    document: Document,
    config_resolver: ConfigResolver = resolve_newsdom_config_from_db,
    request_fn: ParseRequestFn = request_pdf_dom,
) -> str:
    """Recognize one pending workspace-document PDF, or record a safe outcome."""
    from api.data import decode_pending_pdf_document_bytes

    try:
        pdf_bytes = decode_pending_pdf_document_bytes(document)
    except ValueError as exc:
        document.document_status = PDF_DOM_RECOGNITION_FAILED_STATUS
        logger.warning(
            "NewsDOM document %s rejected before recognition: %s",
            getattr(document, "document_id", "?"),
            exc,
        )
        return RESULT_FAILED

    config = await config_resolver(session, document.organization_id)
    if config is None:
        logger.info(
            "NewsDOM document %s remains pending: no active provider for "
            "organization %s.",
            getattr(document, "document_id", "?"),
            document.organization_id or "personal-scope",
        )
        return RESULT_PENDING

    try:
        await recognize_document_pdf(
            document=document,
            pdf_bytes=pdf_bytes,
            config=config,
            request_fn=request_fn,
        )
    except NewsdomConfigurationError as exc:
        logger.warning(
            "NewsDOM document %s remains pending: provider configuration was "
            "rejected: %s",
            getattr(document, "document_id", "?"),
            exc,
        )
        return RESULT_PENDING
    except (NewsdomRequestError, ValueError) as exc:
        document.document_status = PDF_DOM_RECOGNITION_FAILED_STATUS
        logger.warning(
            "NewsDOM document %s recognition failed: %s",
            getattr(document, "document_id", "?"),
            exc,
        )
        return RESULT_FAILED
    return RESULT_RECOGNIZED


def _engine_uses_postgresql() -> bool:
    """Return whether advisory-lock SQL is supported by the configured engine."""
    return engine.dialect.name == "postgresql"


async def _try_acquire_sweep_lease(connection: AsyncConnection) -> bool:
    """Become the sweep leader for this cycle on this dedicated connection.

    Takes an ``AsyncConnection`` rather than the per-item ``AsyncSession``
    deliberately: ``AsyncSession.commit()``/``rollback()`` release their
    underlying connection back to the pool on every call (SQLAlchemy's normal
    "connectionless execution" behavior), so acquiring the lock through that
    session risks releasing it -- or never releasing it -- from a *different*
    physical backend connection than the one PostgreSQL actually granted the
    advisory lock to. Advisory locks are scoped to the acquiring backend
    session, so a mismatched unlock is a silent no-op and the lock stays held
    (blocking every replica's sweep) until the stray connection is eventually
    recycled or closed. Mirrors
    ``services.attachment_reparse_worker._try_acquire_sweep_lease``.

    Sets AUTOCOMMIT on this connection first: without it, the advisory-lock
    SELECT below opens an implicit transaction that would otherwise stay
    open and idle on this connection for the whole sweep (every other
    statement runs through the separate per-item session), risking
    PostgreSQL's ``idle_in_transaction_session_timeout`` killing this
    connection mid-sweep and silently dropping the lease.
    """
    await connection.execution_options(isolation_level="AUTOCOMMIT")
    acquired = await connection.scalar(
        select(
            func.pg_try_advisory_lock(
                func.hashtext(bindparam("namespace_key")),
                func.hashtext(bindparam("sweep_key")),
            )
        ),
        _SWEEP_LOCK_PARAMS,
    )
    return bool(acquired)


async def _release_sweep_lease(connection: AsyncConnection) -> None:
    """Release the PostgreSQL advisory lock on the connection that holds it."""
    await connection.scalar(
        select(
            func.pg_advisory_unlock(
                func.hashtext(bindparam("namespace_key")),
                func.hashtext(bindparam("sweep_key")),
            )
        ),
        _SWEEP_LOCK_PARAMS,
    )


class NewsdomRecognitionWorker:
    """Periodically recognize pending PDF attachments and workspace documents.

    Mirrors :class:`ReplySlaScheduler`: a jittered periodic loop, a PostgreSQL
    advisory-lock lease so only one replica sweeps per cycle, and per-item
    error isolation. Items whose organization has no active NewsDOM provider are
    left pending (they recognize once a provider is configured); unusable
    payloads/responses are marked failed rather than parsed. The lease is
    acquired and released on one dedicated connection held open for the
    whole sweep, and each row is re-fetched fresh by id before processing --
    the same two corrections applied to
    :class:`services.attachment_reparse_worker.AttachmentReparseWorker`,
    which shares this same lease/cursor/per-item-isolation design.
    """

    def __init__(
        self,
        *,
        interval_seconds: int = DEFAULT_NEWSDOM_INTERVAL_SECONDS,
        batch_limit: int = DEFAULT_NEWSDOM_BATCH_LIMIT,
        request_fn: ParseRequestFn = request_pdf_dom,
        config_resolver: ConfigResolver = resolve_newsdom_config_from_db,
    ):
        """Configure the sweep cadence, batch size, and injectable adapters."""
        self.interval_seconds = interval_seconds
        self.batch_limit = batch_limit
        self._request_fn = request_fn
        self._config_resolver = config_resolver
        self._task: asyncio.Task | None = None
        self._is_running = False
        self._attachment_cursor: int | None = None
        self._document_cursor: tuple[datetime.datetime, str] | None = None
        # Rows a past sweep saw as still-pending (RESULT_PENDING or a raised
        # exception). Retried every sweep via an explicit id filter,
        # independent of the forward cursor below -- see _sweep_attachments.
        self._attachment_retry_ids: set[int] = set()
        self._document_retry_ids: set[str] = set()
        self._attachment_sweep_count = 0
        self._document_sweep_count = 0

    async def start(self) -> None:
        """Start the recognition loop once."""
        if self._is_running:
            logger.warning("NewsdomRecognitionWorker is already running.")
            return
        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("NewsdomRecognitionWorker started.")

    async def stop(self) -> None:
        """Cancel and await the active recognition loop."""
        if not self._is_running:
            return
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                logger.debug("NewsdomRecognitionWorker cancellation acknowledged.")
        logger.info("NewsdomRecognitionWorker stopped.")

    async def _run_loop(self) -> None:
        """Run jittered recognition sweeps until stopped."""
        try:
            await asyncio.sleep(
                _sysrand.uniform(
                    0, min(self.interval_seconds / 10, MAX_STARTUP_JITTER_SECONDS)
                )
            )
        except asyncio.CancelledError:
            return

        while self._is_running:
            try:
                await self._sweep()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.error("Error in NewsdomRecognitionWorker loop.", exc_info=True)
            if self._is_running:
                try:
                    await asyncio.sleep(self.interval_seconds)
                except asyncio.CancelledError:
                    break

    async def _sweep(self) -> None:
        """Process one leased attachment and document sweep.

        The advisory lock (when the engine supports it) is acquired and
        released on one dedicated connection held open for the whole sweep --
        never through the per-item ``AsyncSession`` used by
        ``_sweep_attachments``/``_sweep_documents``. See
        ``_try_acquire_sweep_lease`` for why that distinction matters.
        """
        if not _engine_uses_postgresql():
            async with AsyncSessionLocal() as session:
                await self._sweep_attachments(session)
                await self._sweep_documents(session)
            return
        async with engine.connect() as lock_connection:
            if not await _try_acquire_sweep_lease(lock_connection):
                logger.debug(
                    "NewsDOM recognition sweep skipped: another replica holds "
                    "the lease."
                )
                return
            try:
                async with AsyncSessionLocal() as session:
                    await self._sweep_attachments(session)
                    await self._sweep_documents(session)
            finally:
                await _release_sweep_lease(lock_connection)

    async def _sweep_attachments(self, session: AsyncSession) -> None:
        """Process a bounded, starvation-free batch of pending attachments.

        Two independent pieces of state make progress unconditional:

        * ``_attachment_cursor`` is a forward-scan position that only ever
          advances (to the highest id seen in a batch) -- so rows the
          worker has never looked at are always reached eventually, no
          matter how many earlier rows stay stuck.
        * ``_attachment_retry_ids`` is the set of ids a past sweep saw as
          still-pending (raised, or returned ``RESULT_PENDING`` -- e.g. no
          active provider configured for its organization yet). These are
          retried every sweep via an explicit ``id IN (...)`` filter,
          independent of the cursor, and dropped from the set once they
          resolve.

        An earlier version capped the cursor itself at the first unresolved
        row instead of tracking a separate retry set. That avoided losing
        track of one stuck row, but pinned the *entire batch window* behind
        it: once more than ``batch_limit`` consecutive rows were
        permanently stuck (e.g. one organization bulk-imports a burst of
        PDFs before ever configuring a provider), the same stuck rows filled
        every batch forever and nothing past them was ever reached --
        confirmed by reproduction, not merely suspected (300 rows, one
        permanently-stuck row: converges; 60 consecutive permanently-stuck
        rows with batch_limit=50: never converges). Decoupling "retry this
        stuck row" from "where the forward scan has reached" fixes both
        shapes of starvation at once. Each row is also re-fetched fresh by
        id rather than reusing the bulk-loaded instance:
        ``AsyncSession.rollback()`` expires every object already loaded in
        this session, and ``process_pending_attachment`` reads
        attachment/email attributes synchronously, so a stale, expired
        instance from an earlier item's failure would raise on that read
        instead of just isolating the one failure. Mirrors
        ``services.attachment_reparse_worker.AttachmentReparseWorker._sweep_attachments``.

        Neither piece of state can discover a row that gets explicitly
        re-marked pending *after* the cursor already passed it -- e.g. an
        already-recognized attachment whose organization requests it be
        looked at again. It was never seen as unresolved by this worker (so
        it's not in the retry set) and its id no longer satisfies
        ``id > cursor``. Every ``FULL_RESCAN_EVERY_N_SWEEPS``-th sweep forces
        a full rescan (cursor reset to ``None``) to bound how stale such a
        row can get; this is always safe regardless of cadence, since the
        ``parse_status`` filter already excludes every row that's actually
        resolved, so a full rescan only ever widens the candidate set.
        """
        self._attachment_sweep_count += 1
        if self._attachment_sweep_count % FULL_RESCAN_EVERY_N_SWEEPS == 0:
            self._attachment_cursor = None
        rows = await self._load_pending_attachments(session)
        batch_ids = [attachment.id for attachment in rows]
        processed_ids: set[int] = set()
        unresolved_ids: set[int] = set()
        for attachment_id in batch_ids:
            processed_ids.add(attachment_id)
            try:
                attachment = await session.get(
                    Attachment,
                    attachment_id,
                    options=[selectinload(Attachment.email)],
                )
                if attachment is None:
                    continue
                result = await process_pending_attachment(
                    session=session,
                    attachment=attachment,
                    config_resolver=self._config_resolver,
                    request_fn=self._request_fn,
                )
                await session.commit()
                if result == RESULT_PENDING:
                    unresolved_ids.add(attachment_id)
                else:
                    logger.info(
                        "NewsDOM attachment %s recognition result: %s",
                        attachment_id,
                        result,
                    )
            except Exception:
                await session.rollback()
                logger.error(
                    "NewsDOM attachment %s recognition raised.",
                    attachment_id,
                    exc_info=True,
                )
                unresolved_ids.add(attachment_id)
        if batch_ids:
            highest_seen = max(batch_ids)
            self._attachment_cursor = (
                highest_seen
                if self._attachment_cursor is None
                else max(self._attachment_cursor, highest_seen)
            )
        self._attachment_retry_ids = (
            self._attachment_retry_ids - processed_ids
        ) | unresolved_ids

    def _pending_attachment_statement(
        self, after_id: int | None, retry_ids: set[int]
    ):
        """Build the next deterministic attachment batch query.

        Selects rows past the forward cursor OR still tracked in
        ``retry_ids``, so a persistently-stuck row keeps getting retried
        without pinning the forward scan behind it. When both are present,
        never-yet-seen forward rows sort before already-tracked retry rows
        (a ``CASE`` bucket ahead of the plain id order) -- otherwise, once
        ``retry_ids`` alone reached ``batch_limit`` in size, ``ORDER BY id``
        would let those (necessarily smaller, already-seen) ids win every
        slot in the ``LIMIT``, starving forward progress right back into the
        bug this is fixing. This does mean retry rows can wait longer under
        sustained, saturating forward load -- a deliberate trade-off, since
        that only delays retrying a handful of already-known-stuck rows,
        never blocks the rest of the pipeline the way the reverse priority
        did.
        """
        statement = select(Attachment).where(
            Attachment.parse_status == PDF_DOM_RECOGNITION_PENDING_STATUS
        )
        # retry_ids only narrows the result when there's a cursor to narrow
        # *against* -- with no cursor yet (after_id is None, including a
        # forced full rescan), every pending row already qualifies, and
        # restricting to just retry_ids here would incorrectly hide
        # everything else that's pending.
        if after_id is not None:
            conditions = [Attachment.id > after_id]
            if retry_ids:
                conditions.append(Attachment.id.in_(retry_ids))
            statement = statement.where(
                conditions[0] if len(conditions) == 1 else or_(*conditions)
            )
        order_columns = []
        if after_id is not None and retry_ids:
            order_columns.append(case((Attachment.id > after_id, 0), else_=1))
        order_columns.append(Attachment.id)
        return (
            statement.order_by(*order_columns)
            .options(selectinload(Attachment.email))
            .limit(self.batch_limit)
        )

    async def _load_pending_attachments(
        self, session: AsyncSession
    ) -> list[Attachment]:
        """Load the next batch: past the cursor, plus any known-stuck rows."""
        return (
            (
                await session.execute(
                    self._pending_attachment_statement(
                        self._attachment_cursor, self._attachment_retry_ids
                    )
                )
            )
            .scalars()
            .all()
        )

    async def _sweep_documents(self, session: AsyncSession) -> None:
        """Process a bounded, starvation-free batch of pending documents.

        Same design as ``_sweep_attachments`` -- a monotonically-advancing
        forward cursor plus a persistent ``_document_retry_ids`` set for
        rows that raised or came back ``RESULT_PENDING`` (no active provider
        configured for its organization yet), retried every sweep
        independent of the cursor. See ``_sweep_attachments`` for why a
        cursor that instead capped itself at the first unresolved row let
        more than ``batch_limit`` consecutive stuck rows starve everything
        past them -- the same fix applies here.

        Unlike ``Attachment.id`` (an auto-incrementing integer, monotonic
        with insertion order), ``Document.document_id`` defaults to a random
        UUID (``f"doc_{uuid.uuid4().hex}"``) -- not monotonic at all. A
        document inserted *after* the cursor already advanced can still sort
        lexicographically *below* it; since it was never seen before, it is
        not in the retry set either, so it would never be selected again --
        confirmed by Devin Review and by direct inspection of the model.
        ``_document_cursor`` is therefore a ``(created_at, document_id)``
        tuple: ``created_at`` (a Python-side timestamp set at insert time)
        is genuinely monotonic with insertion order, and ``document_id``
        only breaks ties between rows inserted in the same instant.

        Neither the cursor nor the retry set can discover a document
        explicitly re-marked pending after the cursor already passed it --
        e.g. ``POST .../pdf-dom-recognition-intent`` re-triggering
        recognition on an already-resolved document. Every
        ``FULL_RESCAN_EVERY_N_SWEEPS``-th sweep forces a full rescan
        (cursor reset to ``None``) to bound how stale such a row can get;
        see ``_sweep_attachments`` for why this is always safe.
        """
        self._document_sweep_count += 1
        if self._document_sweep_count % FULL_RESCAN_EVERY_N_SWEEPS == 0:
            self._document_cursor = None
        rows = await self._load_pending_documents(session)
        processed_ids: set[str] = set()
        unresolved_ids: set[str] = set()
        # (created_at, document_id) pairs captured from the freshly re-fetched
        # instance only -- never from the bulk-loaded `rows` list, which may
        # hold an instance a *prior* item's rollback already expired.
        seen_pairs: list[tuple[datetime.datetime, str]] = []
        for document_id in [document.document_id for document in rows]:
            processed_ids.add(document_id)
            try:
                document = await session.get(Document, document_id)
                if document is None:
                    continue
                seen_pairs.append((document.created_at, document.document_id))
                result = await process_pending_document(
                    session=session,
                    document=document,
                    config_resolver=self._config_resolver,
                    request_fn=self._request_fn,
                )
                await session.commit()
                if result == RESULT_PENDING:
                    unresolved_ids.add(document_id)
                else:
                    logger.info(
                        "NewsDOM document %s recognition result: %s",
                        document_id,
                        result,
                    )
            except Exception:
                await session.rollback()
                logger.error(
                    "NewsDOM document %s recognition raised.",
                    document_id,
                    exc_info=True,
                )
                unresolved_ids.add(document_id)
        if seen_pairs:
            highest_seen = max(seen_pairs)
            self._document_cursor = (
                highest_seen
                if self._document_cursor is None
                else max(self._document_cursor, highest_seen)
            )
        self._document_retry_ids = (
            self._document_retry_ids - processed_ids
        ) | unresolved_ids

    def _pending_document_statement(
        self,
        after_cursor: tuple[datetime.datetime, str] | None,
        retry_ids: set[str],
    ):
        """Build the next deterministic workspace-document batch query.

        Selects rows past the forward ``(created_at, document_id)`` cursor
        OR still tracked in ``retry_ids``, and orders forward rows ahead of
        retry rows when both are present, exactly like
        ``_pending_attachment_statement`` (see its docstring for why the
        priority must run that way). The forward comparison is a row-value
        (tuple) comparison -- ``created_at`` first, ``document_id`` only to
        break same-instant ties -- so it stays correct however
        ``document_id`` sorts.
        """
        statement = select(Document).where(
            Document.document_status == PDF_DOM_RECOGNITION_PENDING_STATUS
        )
        forward_condition = None
        if after_cursor is not None:
            after_created_at, after_document_id = after_cursor
            forward_condition = or_(
                Document.created_at > after_created_at,
                and_(
                    Document.created_at == after_created_at,
                    Document.document_id > after_document_id,
                ),
            )
        # retry_ids only narrows the result when there's a cursor to narrow
        # *against* -- see _pending_attachment_statement for why (identical
        # reasoning, shared between both sweeps).
        if forward_condition is not None:
            conditions = [forward_condition]
            if retry_ids:
                conditions.append(Document.document_id.in_(retry_ids))
            statement = statement.where(
                conditions[0] if len(conditions) == 1 else or_(*conditions)
            )
        order_columns = []
        if forward_condition is not None and retry_ids:
            order_columns.append(case((forward_condition, 0), else_=1))
        order_columns.extend([Document.created_at, Document.document_id])
        return statement.order_by(*order_columns).limit(self.batch_limit)

    async def _load_pending_documents(self, session: AsyncSession) -> list[Document]:
        """Load the next batch: past the cursor, plus any known-stuck rows."""
        return (
            (
                await session.execute(
                    self._pending_document_statement(
                        self._document_cursor, self._document_retry_ids
                    )
                )
            )
            .scalars()
            .all()
        )
