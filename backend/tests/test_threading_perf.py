import pytest

from services.threading_service import assign_thread_id


class _Result:
    def all(self):
        return []


class _CountingSession:
    def __init__(self):
        self.execute_count = 0
        self.queries = []

    async def execute(self, query):
        self.execute_count += 1
        self.queries.append(query)
        return _Result()


@pytest.mark.asyncio
async def test_assign_thread_id_batches_many_reference_lookups():
    session = _CountingSession()
    references = " ".join(f"<ref{i}@example.com>" for i in range(100))

    thread_id = await assign_thread_id(
        session,
        {
            "message_id": "<reply@example.com>",
            "in_reply_to": "<parent@example.com>",
            "references": references,
        },
        user_id="testuser",
        organization_id="org-acme",
        workspace_id="workspace-a",
    )

    assert thread_id == "ref0@example.com"
    assert session.execute_count == 1
    assert "email_records.message_id" in str(session.queries[0]).lower()
