import logging
import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.schema import UniqueConstraint

import services.email_import_service as email_import_module
from services.exceptions import EmailParseError, EmbeddingGenerationError
from services.batch_embedding_service import BatchEmbeddingPartial
from services.email_import_service import (
    EmailImportBatchContext,
    EMBEDDING_DIMENSION,
    EmailImportEmbeddingProvider,
    MAX_EMBEDDING_CHUNKS_PER_WINDOW,
    _generate_import_embeddings,
)
from db.models import Email


def test_email_identity_includes_workspace_scope():
    constraint = next(
        item
        for item in Email.__table__.constraints
        if isinstance(item, UniqueConstraint)
        and item.name == "uq_emails_workspace_message"
    )
    assert tuple(column.name for column in constraint.columns) == (
        "user_id",
        "organization_id",
        "workspace_id",
        "message_id",
    )


@pytest.mark.asyncio
async def test_duplicate_lookup_is_scoped_to_target_workspace():
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    await email_import_module._find_existing_email(
        session,
        user_id="user-1",
        organization_id="org-1",
        workspace_id="workspace-blue",
        message_id="message@example.com",
        fingerprint="fingerprint-1",
    )

    statement = session.execute.await_args.args[0]
    assert "email_records.workspace_id" in str(statement)


def test_import_transport_ceiling_accepts_sources_over_20_mib():
    assert email_import_module.MAX_IMPORT_UPLOAD_BYTES > 20 * 1024 * 1024


@pytest.mark.parametrize(
    "input_name,expected",
    [
        ("file.zip", "file.zip"),
        ("", "upload"),
        (None, "upload"),
        ("/some/path/file.zip", "file.zip"),
        ("  spaced.zip  ", "spaced.zip"),
        ("/", "upload"),
        (".", "upload"),
        ("..", "upload"),
        ("/tmp/..", "upload"),  # nosec B108
        ("%2e%2e%2fupload", "upload"),
        ("%252e%252e%252fupload", "upload"),
        ("%2e%2e%5csecret.eml", "secret.eml"),
        ("..\\..\\upload", "upload"),
        ("..%5c..%5cupload", "upload"),
        ("%00secret.eml", "upload"),
        ("%0asecret.eml", "upload"),
        ("%C2%85secret.eml", "upload"),
        ("secret\u202eeml", "upload"),
        ("회의.eml", "회의.eml"),
    ],
)
def test_safe_upload_filename(input_name, expected):
    assert email_import_module._safe_upload_filename(input_name) == expected


def test_safe_upload_filename_fails_closed_beyond_decode_round_limit():
    encoded_name = "%2e%2e%2fsecret.eml"
    for _ in range(email_import_module.MAX_UPLOAD_FILENAME_DECODE_ROUNDS):
        encoded_name = encoded_name.replace("%", "%25")

    assert email_import_module._safe_upload_filename(encoded_name) == "upload"


@pytest.mark.parametrize(
    ("input_name", "expected"),
    [
        ("message.eml", "message.eml"),
        ("MESSAGE.EML", "MESSAGE.EML"),
        ("%2e%2e%5cmessage.eml", "message.eml"),
        ("%00message.eml", None),
        ("%0amessage.eml", None),
        ("secret.eml%00.zip", None),
        ("payload.exe", None),
    ],
)
def test_canonical_email_import_upload_filename(input_name, expected):
    assert (
        email_import_module.canonical_email_import_upload_filename(input_name)
        == expected
    )


@pytest.mark.parametrize(
    "upload_name,eml_path,expected",
    [
        # without eml_path
        ("my_archive.zip", None, "my_archive.zip"),
        ("", None, "upload"),
        ("/path/to/my_archive.zip", None, "my_archive.zip"),
        # matching eml_path
        ("my_file.eml", Path("my_file.eml"), "my_file.eml"),
        ("/path/my_file.eml", Path("/other/path/my_file.eml"), "my_file.eml"),
        ("  my_file.eml  ", Path("my_file.eml"), "my_file.eml"),
        # differing eml_path
        ("my_archive.zip", Path("email_1.eml"), "my_archive.zip:email_1.eml"),
        (
            "/path/my_archive.zip",
            Path("/some/folder/email_1.eml"),
            "my_archive.zip:email_1.eml",
        ),
        ("", Path("email_1.eml"), "upload:email_1.eml"),
        (
            "my_archive.zip",
            Path("ok\nforged.eml"),
            "my_archive.zip:upload",
        ),
        (
            "my_archive.zip",
            Path("safe\u202ename.eml"),
            "my_archive.zip:upload",
        ),
    ],
)
def test_safe_item_filename(upload_name, eml_path, expected):
    assert email_import_module._safe_item_filename(upload_name, eml_path) == expected


def test_build_email_object_attaches_content_graph_records():
    parsed = {
        "message_id": "<graph@example.com>",
        "sender": "sender@example.com",
        "reply_to": None,
        "recipients": "owner@example.com",
        "subject": "Graph",
        "in_reply_to": None,
        "references": None,
        "body": "Launch\n\nHello team",
        "body_parse_content": "<h1>Launch</h1><p>Hello <strong>team</strong></p>",
        "body_content_type": "text/html",
        "attachments": [
            {
                "filename": "plan.md",
                "content": "# Plan\n\nShip graph",
                "content_type": "text/markdown",
            }
        ],
    }

    email_obj, attachment_count = email_import_module._build_email_object(
        parsed=parsed,
        user_id="user-1",
        organization_id="org-1",
        message_id="<graph@example.com>",
        thread_id="thread-1",
        fingerprint="fingerprint-1",
        persisted_date=datetime.datetime(2026, 7, 2, tzinfo=datetime.timezone.utc),
        attachment_payloads=list(parsed["attachments"]),
        fitted_embeddings=[
            [0.0] * EMBEDDING_DIMENSION,
            [0.0] * EMBEDDING_DIMENSION,
        ],
    )

    assert attachment_count == 1
    assert [segment.safe_text_content for segment in email_obj.content_segments] == [
        "Launch",
        "Hello team",
        "Plan",
        "Ship graph",
    ]
    assert [segment.segment_kind for segment in email_obj.content_segments] == [
        "heading",
        "paragraph",
        "heading",
        "paragraph",
    ]
    assert email_obj.content_segments[1].heading_path == "Launch"
    assert [node.node_kind for node in email_obj.content_nodes].count("document") == 2
    assert [
        segment.safe_text_content
        for segment in email_obj.attachments[0].content_segments
    ] == ["Plan", "Ship graph"]
    assert {node.source_kind for node in email_obj.content_nodes} == {
        "email_body",
        "attachment",
    }


def test_build_email_object_attaches_knowledge_graph_edges():
    parsed = {
        "message_id": "<graph@example.com>",
        "sender": "sender@example.com",
        "reply_to": None,
        "recipients": "owner@example.com",
        "subject": "Graph",
        "in_reply_to": None,
        "references": None,
        "body": "Launch\n\nHello team",
        "body_parse_content": "<h1>Launch</h1><p>Hello <strong>team</strong></p>",
        "body_content_type": "text/html",
        "attachments": [
            {
                "filename": "plan.md",
                "content": "# Plan\n\nShip graph",
                "content_type": "text/markdown",
            }
        ],
    }

    email_obj, _attachment_count = email_import_module._build_email_object(
        parsed=parsed,
        user_id="user-1",
        organization_id="org-1",
        message_id="<graph@example.com>",
        thread_id="thread-1",
        fingerprint="fingerprint-1",
        persisted_date=datetime.datetime(2026, 7, 2, tzinfo=datetime.timezone.utc),
        attachment_payloads=list(parsed["attachments"]),
        fitted_embeddings=[
            [0.0] * EMBEDDING_DIMENSION,
            [0.0] * EMBEDDING_DIMENSION,
        ],
    )

    edge_kinds = {edge.edge_kind for edge in email_obj.knowledge_graph_edges}
    assert {
        "node_contains_node",
        "node_has_segment",
        "segment_next",
        "heading_contains_segment",
    } <= edge_kinds
    assert len({edge.edge_uid for edge in email_obj.knowledge_graph_edges}) == len(
        email_obj.knowledge_graph_edges
    )
    assert all(
        "<" not in edge.edge_path and ">" not in edge.edge_path
        for edge in email_obj.knowledge_graph_edges
    )

    heading_pairs = {
        (edge.source_segment.safe_text_content, edge.target_segment.safe_text_content)
        for edge in email_obj.knowledge_graph_edges
        if edge.edge_kind == "heading_contains_segment"
    }
    assert ("Launch", "Hello team") in heading_pairs
    assert ("Plan", "Ship graph") in heading_pairs

    next_pairs = {
        (edge.source_segment.safe_text_content, edge.target_segment.safe_text_content)
        for edge in email_obj.knowledge_graph_edges
        if edge.edge_kind == "segment_next"
    }
    assert ("Launch", "Hello team") in next_pairs
    assert ("Plan", "Ship graph") in next_pairs


def test_build_email_object_persists_attachment_parse_metadata():
    parsed = {
        "message_id": "<attachments@example.com>",
        "sender": "sender@example.com",
        "reply_to": None,
        "recipients": "owner@example.com",
        "subject": "Attachments",
        "in_reply_to": None,
        "references": None,
        "body": "See attached",
        "body_content_type": "text/plain",
        "body_parse_content": "See attached",
        "attachments": [
            {
                "filename": "page.html",
                "content": "Launch Ship",
                "content_type": "text/html",
                "parse_content": "<h1>Launch</h1><p>Ship</p>",
                "parse_content_type": "text/html",
                "parser_key": "html",
                "parse_status": "parsed",
                "parse_error_code": None,
            },
            {
                "filename": "contract.pdf",
                "content": "",
                "content_type": "application/pdf",
                "parse_content": "",
                "parse_content_type": "application/pdf",
                "parser_key": "unsupported_binary",
                "parse_status": "unsupported_content_type",
                "parse_error_code": "unsupported_content_type",
            },
        ],
    }

    email_obj, attachment_count = email_import_module._build_email_object(
        parsed=parsed,
        user_id="user-1",
        organization_id="org-1",
        message_id="<attachments@example.com>",
        thread_id="thread-1",
        fingerprint="fingerprint-1",
        persisted_date=datetime.datetime(2026, 7, 2, tzinfo=datetime.timezone.utc),
        attachment_payloads=list(parsed["attachments"]),
        fitted_embeddings=[
            [0.0] * EMBEDDING_DIMENSION,
            [0.0] * EMBEDDING_DIMENSION,
            [0.0] * EMBEDDING_DIMENSION,
        ],
    )

    assert attachment_count == 2
    assert [
        (
            attachment.filename,
            attachment.content_type,
            attachment.parse_content_type,
            attachment.parser_key,
            attachment.parse_status,
        )
        for attachment in email_obj.attachments
    ] == [
        ("page.html", "text/html", "text/html", "html", "parsed"),
        (
            "contract.pdf",
            "application/pdf",
            "application/pdf",
            "unsupported_binary",
            "unsupported_content_type",
        ),
    ]
    assert email_obj.attachments[1].parse_error_code == "unsupported_content_type"
    assert [
        segment.safe_text_content
        for segment in email_obj.attachments[0].content_segments
    ] == ["Launch", "Ship"]
    assert email_obj.attachments[1].content_segments == []


def test_build_email_object_attaches_structured_non_pdf_content_graph_records():
    parsed = {
        "message_id": "<structured@example.com>",
        "sender": "sender@example.com",
        "reply_to": None,
        "recipients": "owner@example.com",
        "subject": "Structured attachments",
        "in_reply_to": None,
        "references": None,
        "body": "See attached",
        "body_content_type": "text/plain",
        "body_parse_content": "See attached",
        "attachments": [
            {
                "filename": "status.json",
                "content": '{"project":"Launch"}',
                "content_type": "application/json",
                "parse_content": '{"project":"Launch"}',
                "parse_content_type": "application/json",
                "parser_key": "json",
                "parse_status": "parsed",
                "parse_error_code": None,
            },
            {
                "filename": "status.csv",
                "content": "name,status Launch,Ready",
                "content_type": "text/csv",
                "parse_content": "name,status\nLaunch,Ready",
                "parse_content_type": "text/csv",
                "parser_key": "csv",
                "parse_status": "parsed",
                "parse_error_code": None,
            },
            {
                "filename": "status.xml",
                "content": "Launch",
                "content_type": "application/xml",
                "parse_content": "<root>Launch</root>",
                "parse_content_type": "application/xml",
                "parser_key": "xml",
                "parse_status": "parsed",
                "parse_error_code": None,
            },
            {
                "filename": "invite.ics",
                "content": "BEGIN:VCALENDAR SUMMARY:Launch END:VCALENDAR",
                "content_type": "text/calendar",
                "parse_content": "BEGIN:VCALENDAR\nSUMMARY:Launch\nEND:VCALENDAR",
                "parse_content_type": "text/calendar",
                "parser_key": "calendar",
                "parse_status": "parsed",
                "parse_error_code": None,
            },
        ],
    }

    email_obj, attachment_count = email_import_module._build_email_object(
        parsed=parsed,
        user_id="user-1",
        organization_id="org-1",
        message_id="<structured@example.com>",
        thread_id="thread-1",
        fingerprint="fingerprint-1",
        persisted_date=datetime.datetime(2026, 7, 2, tzinfo=datetime.timezone.utc),
        attachment_payloads=list(parsed["attachments"]),
        fitted_embeddings=[
            [0.0] * EMBEDDING_DIMENSION,
            [0.0] * EMBEDDING_DIMENSION,
            [0.0] * EMBEDDING_DIMENSION,
            [0.0] * EMBEDDING_DIMENSION,
            [0.0] * EMBEDDING_DIMENSION,
        ],
    )

    assert attachment_count == 4
    segment_text_by_filename = {
        attachment.filename: [
            segment.safe_text_content for segment in attachment.content_segments
        ]
        for attachment in email_obj.attachments
    }
    assert segment_text_by_filename == {
        "status.json": ["project: Launch"],
        "status.csv": ["name, status", "name=Launch; status=Ready"],
        "status.xml": ["Launch"],
        "invite.ics": ["SUMMARY: Launch"],
    }
    assert {attachment.parser_key for attachment in email_obj.attachments} == {
        "json",
        "csv",
        "xml",
        "calendar",
    }


@pytest.mark.asyncio
async def test_import_single_eml_offloads_read_and_parse(monkeypatch, tmp_path):
    eml_path = tmp_path / "message.eml"
    eml_path.write_bytes(b"From: a@example.com\nTo: b@example.com\n\nbody")
    session = AsyncMock(spec=AsyncSession)
    calls = []

    def fake_read_and_parse(path):
        calls.append(("read_and_parse", path))
        raise EmailParseError("boom")

    async def fake_to_thread(func, *args):
        calls.append(("to_thread", func, args))
        return func(*args)

    monkeypatch.setattr(email_import_module, "_read_and_parse_eml", fake_read_and_parse)
    monkeypatch.setattr(email_import_module.asyncio, "to_thread", fake_to_thread)

    result = await email_import_module._import_single_eml(
        session,
        eml_path=eml_path,
        display_filename="message.eml",
        user_id="user-1",
        organization_id="org-1",
    )

    assert result.status == "failed"
    assert result.reason_code == "parse_failed"
    assert calls == [
        ("to_thread", fake_read_and_parse, (eml_path,)),
        ("read_and_parse", eml_path),
    ]
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_eml_paths_for_upload_offloads_upload_write(monkeypatch, tmp_path):
    upload = email_import_module.EmailImportUpload(
        filename="message.eml",
        content=b"From: a@example.com\nTo: b@example.com\n\nbody",
    )
    calls = []

    async def fake_to_thread(func, *args):
        calls.append((func, args))
        return func(*args)

    monkeypatch.setattr(email_import_module.asyncio, "to_thread", fake_to_thread)

    eml_paths, failure_reason = await email_import_module._eml_paths_for_upload(
        upload=upload,
        upload_dir=tmp_path,
    )

    assert failure_reason is None
    assert eml_paths == [tmp_path / "message.eml"]
    assert len(calls) == 1
    assert getattr(calls[0][0], "__self__", None) == tmp_path / "message.eml"
    assert calls[0][1] == (upload.content,)
    assert (tmp_path / "message.eml").read_bytes() == upload.content


@pytest.mark.asyncio
async def test_eml_paths_for_upload_reports_write_failure(monkeypatch, tmp_path):
    upload = email_import_module.EmailImportUpload(
        filename="message.eml",
        content=b"not written",
    )

    async def fake_to_thread(func, *args):
        raise OSError("disk full")

    monkeypatch.setattr(email_import_module.asyncio, "to_thread", fake_to_thread)

    eml_paths, failure_reason = await email_import_module._eml_paths_for_upload(
        upload=upload,
        upload_dir=tmp_path,
    )

    assert eml_paths == []
    assert failure_reason == "file_write_failed"
    assert not (tmp_path / "message.eml").exists()


@pytest.mark.asyncio
async def test_import_single_eml_rejects_symlink(tmp_path):
    target_path = tmp_path / "target.txt"
    target_path.write_text("not an eml")
    symlink_path = tmp_path / "message.eml"
    try:
        symlink_path.symlink_to(target_path)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable in this test session: {exc}")
    session = AsyncMock(spec=AsyncSession)

    result = await email_import_module._import_single_eml(
        session,
        eml_path=symlink_path,
        display_filename="message.eml",
        user_id="user-1",
        organization_id="org-1",
    )

    assert result.status == "failed"
    assert result.reason_code == "parse_failed"
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_generate_import_embeddings_logs_non_secret_provider_fallback(caplog):
    provider = EmailImportEmbeddingProvider(
        api_key="secret-provider-token",
        base_url="http://ollama:11434/v1",
        embedding_model="embeddinggemma",
    )
    caplog.set_level(logging.WARNING, logger="services.email_import_service")

    with patch(
        "services.email_import_service.generate_embeddings",
        new_callable=AsyncMock,
    ) as mock_generate_embeddings:
        mock_generate_embeddings.side_effect = EmbeddingGenerationError(
            "secret-provider-token unavailable at http://ollama:11434/v1"
        )

        embeddings = await _generate_import_embeddings(
            ["Provider body"],
            embedding_provider=provider,
        )

    assert embeddings == [[0.0] * EMBEDDING_DIMENSION]
    assert "Email import embedding generation failed" in caplog.text
    assert "retrying imported content item by item" in caplog.text
    assert "error_type=EmbeddingGenerationError" in caplog.text
    assert "text_count=1" in caplog.text
    assert "secret-provider-token" not in caplog.text
    assert "ollama" not in caplog.text
    assert "embeddinggemma" not in caplog.text


@pytest.mark.asyncio
async def test_extract_embeddings_chunks_long_sources_and_averages_vectors():
    provider = EmailImportEmbeddingProvider(
        api_key="provider-key",
        base_url="https://provider.example/v1",
        embedding_model="text-embedding-3-large",
    )
    captured_texts: list[str] = []
    next_embedding = 1

    async def fake_generate(texts, *, embedding_provider, batch_context=None):
        nonlocal next_embedding
        captured_texts.extend(texts)
        embeddings = [
            [float(index)] * EMBEDDING_DIMENSION
            for index in range(next_embedding, next_embedding + len(texts))
        ]
        next_embedding += len(texts)
        return embeddings

    parsed = {
        "body": "body paragraph " * 3000,
        "attachments": [{"content": "short attachment"}, {"content": ""}],
    }
    with patch(
        "services.email_import_service._generate_import_embeddings",
        side_effect=fake_generate,
    ):
        _, embeddings = await email_import_module._extract_and_generate_embeddings(
            parsed,
            provider,
        )

    body_chunk_count = len(captured_texts) - 1
    assert body_chunk_count > 1
    assert len(embeddings) == 3
    assert "" not in captured_texts
    assert embeddings[0][0] == sum(range(1, body_chunk_count + 1)) / body_chunk_count
    assert embeddings[1][0] == float(len(captured_texts))
    assert embeddings[2] == [0.0] * EMBEDDING_DIMENSION


@pytest.mark.asyncio
async def test_partial_batch_falls_back_only_for_unfinished_sources():
    provider = EmailImportEmbeddingProvider(
        api_key="provider-key",
        base_url="https://provider.example/v1",
        embedding_model="text-embedding-test",
    )
    partial = BatchEmbeddingPartial(
        completed_vectors=[[0.25] * EMBEDDING_DIMENSION],
        pending_texts=["pending source"],
    )

    with (
        patch(
            "services.email_import_service.try_batch_import_embeddings",
            new_callable=AsyncMock,
            return_value=partial,
        ) as mock_batch,
        patch(
            "services.email_import_service.generate_embeddings",
            new_callable=AsyncMock,
            return_value=[[0.75] * EMBEDDING_DIMENSION],
        ) as mock_generate,
    ):
        embeddings = await _generate_import_embeddings(
            ["completed source", "pending source"],
            embedding_provider=provider,
            batch_context=EmailImportBatchContext(
                session=None, user_id="user-1", organization_id="org-acme"
            ),
        )

    mock_batch.assert_awaited_once()
    assert mock_generate.await_args.args[0] == ["pending source"]
    assert embeddings == [[0.25] * EMBEDDING_DIMENSION, [0.75] * EMBEDDING_DIMENSION]


@pytest.mark.asyncio
async def test_partial_batch_fallback_keeps_provider_windows_bounded():
    provider = EmailImportEmbeddingProvider(
        api_key="provider-key",
        base_url="https://provider.example/v1",
        embedding_model="text-embedding-test",
    )
    pending_texts = [
        f"pending source {index}"
        for index in range(MAX_EMBEDDING_CHUNKS_PER_WINDOW * 2 + 1)
    ]
    partial = BatchEmbeddingPartial(
        completed_vectors=[[0.25] * EMBEDDING_DIMENSION],
        pending_texts=pending_texts,
    )

    with (
        patch(
            "services.email_import_service.try_batch_import_embeddings",
            new_callable=AsyncMock,
            return_value=partial,
        ),
        patch(
            "services.email_import_service.generate_embeddings",
            new_callable=AsyncMock,
            side_effect=lambda texts, _api_key, **_kwargs: [
                [0.75] * EMBEDDING_DIMENSION for _ in texts
            ],
        ) as mock_generate,
    ):
        embeddings = await _generate_import_embeddings(
            ["completed source", *pending_texts],
            embedding_provider=provider,
            batch_context=EmailImportBatchContext(
                session=None, user_id="user-1", organization_id="org-acme"
            ),
        )

    assert [len(call.args[0]) for call in mock_generate.await_args_list] == [
        MAX_EMBEDDING_CHUNKS_PER_WINDOW,
        MAX_EMBEDDING_CHUNKS_PER_WINDOW,
        1,
    ]
    assert len(embeddings) == len(pending_texts) + 1
    assert embeddings[0] == [0.25] * EMBEDDING_DIMENSION


@pytest.mark.asyncio
async def test_extract_embeddings_prefers_parsed_body_content():
    captured_texts: list[str] = []

    async def fake_generate(texts, *, embedding_provider, batch_context=None):
        captured_texts.extend(texts)
        return [[0.25] * EMBEDDING_DIMENSION for _ in texts]

    parsed = {
        "body": "raw html source",
        "body_parse_content": "safe parsed body",
        "attachments": [],
    }
    with patch(
        "services.email_import_service._generate_import_embeddings",
        side_effect=fake_generate,
    ):
        _, embeddings = await email_import_module._extract_and_generate_embeddings(
            parsed,
            embedding_provider=None,
        )

    assert captured_texts == ["safe parsed body"]
    assert embeddings == [[0.25] * EMBEDDING_DIMENSION]


@pytest.mark.asyncio
async def test_extract_embeddings_does_not_chunk_pending_attachment_payload():
    captured_texts: list[str] = []

    async def fake_generate(texts, *, embedding_provider, batch_context=None):
        captured_texts.extend(texts)
        return []

    parsed = {
        "body": "",
        "attachments": [
            {
                "content": "cHJpdmF0ZS1wZGYtYnl0ZXM=",
                "parse_status": "pdf_dom_recognition_pending",
            }
        ],
    }
    with patch(
        "services.email_import_service._generate_import_embeddings",
        side_effect=fake_generate,
    ):
        _, embeddings = await email_import_module._extract_and_generate_embeddings(
            parsed,
            embedding_provider=None,
        )

    assert captured_texts == []
    assert embeddings == [[0.0] * EMBEDDING_DIMENSION, [0.0] * EMBEDDING_DIMENSION]


@pytest.mark.asyncio
async def test_extract_embeddings_skips_provider_for_empty_sources():
    provider = EmailImportEmbeddingProvider(
        api_key="provider-key",
        base_url="https://provider.example/v1",
        embedding_model="text-embedding-3-large",
    )

    with patch(
        "services.email_import_service.generate_embeddings",
        new_callable=AsyncMock,
    ) as mock_generate_embeddings:
        _, embeddings = await email_import_module._extract_and_generate_embeddings(
            {"body": "", "attachments": []},
            provider,
        )

    mock_generate_embeddings.assert_not_awaited()
    assert embeddings == [[0.0] * EMBEDDING_DIMENSION]


@pytest.mark.asyncio
async def test_generate_import_embeddings_recovers_valid_items_after_batch_failure():
    provider = EmailImportEmbeddingProvider(
        api_key="secret-provider-token",
        base_url="http://ollama:11434/v1",
        embedding_model="embeddinggemma",
    )

    with patch(
        "services.email_import_service.generate_embeddings",
        new_callable=AsyncMock,
    ) as mock_generate_embeddings:
        mock_generate_embeddings.side_effect = [
            EmbeddingGenerationError("batch failed"),
            [[0.25] * EMBEDDING_DIMENSION],
            EmbeddingGenerationError("single item failed"),
            [[0.75] * (EMBEDDING_DIMENSION // 2)],
        ]

        embeddings = await _generate_import_embeddings(
            ["body", "bad attachment", "good attachment"],
            embedding_provider=provider,
        )

    assert mock_generate_embeddings.await_count == 4
    assert mock_generate_embeddings.await_args_list[1].args[0] == ["body"]
    assert mock_generate_embeddings.await_args_list[2].args[0] == ["bad attachment"]
    assert mock_generate_embeddings.await_args_list[3].args[0] == ["good attachment"]
    assert embeddings[0] == [0.25] * EMBEDDING_DIMENSION
    assert embeddings[1] == [0.0] * EMBEDDING_DIMENSION
    assert embeddings[2] == [0.75] * (EMBEDDING_DIMENSION // 2) + [0.0] * (
        EMBEDDING_DIMENSION // 2
    )


@pytest.mark.asyncio
async def test_persist_project_graph_projection_uses_the_resolved_workspace_id():
    # _persist_project_graph_projection recomputed its own workspace_id
    # (f"workspace-{organization_id}") instead of taking the caller's already
    # -resolved workspace_id -- so a non-default import workspace put the
    # Email row in one workspace and its derived project-graph objects in a
    # different one.
    class _FakeExtraction:
        objects = ["placeholder-object"]

    captured = {}

    class _FakeSession:
        async def commit(self):
            pass

        async def rollback(self):
            pass

    async def fake_extract(*args, **kwargs):
        return _FakeExtraction()

    async def fake_persist(session, *, extraction, user_id, organization_id, workspace_id):
        captured["workspace_id"] = workspace_id

    with (
        patch.object(
            email_import_module,
            "_extract_project_semantics_for_import",
            fake_extract,
        ),
        patch.object(
            email_import_module, "persist_project_graph_projection", fake_persist
        ),
    ):
        await email_import_module._persist_project_graph_projection(
            _FakeSession(),
            ["segment"],
            user_id="user-1",
            organization_id="org-1",
            workspace_id="workspace-custom",
        )

    assert captured["workspace_id"] == "workspace-custom"
