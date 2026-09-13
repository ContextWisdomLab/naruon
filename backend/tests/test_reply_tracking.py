import pytest
import datetime
from api.emails import EmailListItem
from db.models import Email, TenantConfig


class ReplyTrackingResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None


class ReplyTrackingSession:
    def __init__(self, tenant_config, emails):
        self.tenant_config = tenant_config
        self.emails = emails
        self.queries = []

    async def execute(self, query):
        self.queries.append(query)
        if "tenant_configs" in str(query).lower():
            rows = [] if self.tenant_config is None else [self.tenant_config]
            return ReplyTrackingResult(rows)
        return ReplyTrackingResult(self.emails)


def compiled_query_text(query) -> str:
    return str(query).lower()


def compiled_query_params(query) -> dict[str, object]:
    return dict(query.compile().params)


@pytest.mark.asyncio
async def test_identifying_sent_emails_awaiting_replies():
    from services.reply_tracking_service import check_missing_replies

    email_awaiting = Email(
        id=1,
        user_id="user_1",
        organization_id="org_1",
        sender="Me <my@email.com>",
        recipients="other@email.com",
        date=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3),
        body="Please reply by tomorrow.",
        thread_id="thread_1",
    )
    config_mock = TenantConfig(user_id="user_1", smtp_username="my@email.com")
    session = ReplyTrackingSession(config_mock, [email_awaiting])

    flagged_emails = await check_missing_replies(
        session, "user_1", "org_1", "workspace-a"
    )

    assert len(flagged_emails) == 1
    assert flagged_emails[0].id == 1


@pytest.mark.asyncio
async def test_missing_reply_tracking_excludes_answered_and_non_intent_threads():
    from services.reply_tracking_service import check_missing_replies

    sent_answered = Email(
        id=2,
        user_id="user_1",
        organization_id="org_1",
        sender="my@email.com",
        recipients="other@email.com",
        date=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3),
        body="Please reply by tomorrow.",
        thread_id="thread_answered",
    )
    external_reply = Email(
        id=3,
        user_id="user_1",
        organization_id="org_1",
        sender="other@email.com",
        recipients="my@email.com",
        date=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2),
        body="I replied.",
        thread_id="thread_answered",
    )
    sent_without_reply_intent = Email(
        id=4,
        user_id="user_1",
        organization_id="org_1",
        sender="my@email.com",
        recipients="other@email.com",
        date=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1),
        body="FYI only.",
        thread_id="thread_fyi",
    )
    self_sent_note = Email(
        id=5,
        user_id="user_1",
        organization_id="org_1",
        sender="my@email.com",
        recipients="my@email.com",
        date=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1),
        body="Please reply is not a real external follow-up here.",
        thread_id="thread_self",
    )
    config_mock = TenantConfig(user_id="user_1", smtp_username="my@email.com")
    session = ReplyTrackingSession(
        config_mock,
        [sent_answered, external_reply, sent_without_reply_intent, self_sent_note],
    )

    flagged_emails = await check_missing_replies(
        session, "user_1", "org_1", "workspace-a"
    )

    assert flagged_emails == []


@pytest.mark.asyncio
async def test_missing_reply_tracking_groups_bracketed_thread_ids():
    from services.reply_tracking_service import check_missing_replies

    sent_answered = Email(
        id=6,
        user_id="user_1",
        organization_id="org_1",
        message_id="<sent@example.com>",
        thread_id="<root@example.com>",
        sender="my@email.com",
        recipients="other@email.com",
        date=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3),
        body="Please reply by tomorrow.",
    )
    external_reply = Email(
        id=7,
        user_id="user_1",
        organization_id="org_1",
        message_id="<reply@example.com>",
        thread_id="root@example.com",
        sender="other@email.com",
        recipients="my@email.com",
        date=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2),
        body="I replied.",
    )
    config_mock = TenantConfig(user_id="user_1", smtp_username="my@email.com")
    session = ReplyTrackingSession(config_mock, [sent_answered, external_reply])

    flagged_emails = await check_missing_replies(
        session, "user_1", "org_1", "workspace-a"
    )

    assert flagged_emails == []


@pytest.mark.asyncio
async def test_missing_reply_tracking_scopes_email_query_to_user_and_org():
    from services.reply_tracking_service import check_missing_replies

    config_mock = TenantConfig(user_id="user_1", smtp_username="my@email.com")
    session = ReplyTrackingSession(config_mock, [])

    await check_missing_replies(session, "user_1", "org_1", "workspace-a")

    config_query = session.queries[0]
    config_query_text = compiled_query_text(config_query)
    config_query_params = compiled_query_params(config_query)
    assert "tenant_configs.user_id = :user_id_1" in config_query_text
    assert "tenant_configs.organization_id = :organization_id_1" in config_query_text
    assert config_query_params["user_id_1"] == "user_1"
    assert config_query_params["organization_id_1"] == "org_1"

    email_query = session.queries[-1]
    query_text = compiled_query_text(email_query)
    query_params = compiled_query_params(email_query)
    assert "email_records.user_id = :user_id_1" in query_text
    assert "email_records.organization_id = :organization_id_1" in query_text
    assert query_params["user_id_1"] == "user_1"
    assert query_params["organization_id_1"] == "org_1"


@pytest.mark.asyncio
async def test_missing_reply_tracking_uses_provided_tenant_config_without_lookup():
    from services.reply_tracking_service import check_missing_replies

    email_awaiting = Email(
        id=8,
        user_id="user_1",
        organization_id="org_1",
        sender="my@email.com",
        recipients="other@email.com",
        date=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3),
        body="Please reply by tomorrow.",
        thread_id="thread_8",
    )
    config_mock = TenantConfig(user_id="user_1", smtp_username="my@email.com")
    session = ReplyTrackingSession(None, [email_awaiting])

    flagged_emails = await check_missing_replies(
        session,
        "user_1",
        "org_1",
        "workspace-a",
        tenant_config=config_mock,
    )

    assert [email.id for email in flagged_emails] == [8]
    assert all(
        "tenant_configs" not in compiled_query_text(query) for query in session.queries
    )


@pytest.mark.asyncio
async def test_requires_reply_in_email_response():
    # Test that `requires_reply` and `schedule_conflict` are exposed in response
    item = EmailListItem(
        id=1,
        subject="Test",
        sender="sender@test.com",
        date=datetime.datetime.now(datetime.timezone.utc),
        snippet="Test",
        requires_reply=True,
        schedule_conflict=False,
    )
    assert item.requires_reply is True
    assert item.schedule_conflict is False


@pytest.mark.asyncio
async def test_missing_reply_tracking_returns_empty_when_no_user_addresses():
    from services.reply_tracking_service import check_missing_replies

    session = ReplyTrackingSession(None, [])
    flagged_emails = await check_missing_replies(
        session, "user_1", "org_1", "workspace-a"
    )

    assert flagged_emails == []
