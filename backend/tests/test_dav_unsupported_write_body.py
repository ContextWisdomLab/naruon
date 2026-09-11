"""Regression coverage for fail-closed DAV writes without body consumption."""

import asyncio

from fastapi import Request

from api.auth import AuthContext
from api.dav import dav_handler


def test_unsupported_dav_put_rejects_without_consuming_request_body() -> None:
    """A known-unsupported write must not buffer an attacker-controlled body."""
    receive_calls = 0

    async def receive() -> dict[str, object]:
        nonlocal receive_calls
        receive_calls += 1
        return {
            "type": "http.request",
            "body": b"BEGIN:VCALENDAR\r\nEND:VCALENDAR",
            "more_body": False,
        }

    request = Request(
        {
            "type": "http",
            "method": "PUT",
            "headers": [],
            "path": "/dav/user123/projects/file.ics",
            "raw_path": b"/dav/user123/projects/file.ics",
        },
        receive,
    )
    auth_context = AuthContext(
        user_id="user123",
        organization_id="org-acme",
        role="user",
        group_ids=[],
        workspace_id="ws1",
    )

    response = asyncio.run(
        dav_handler(
            request=request,
            path="user123/projects/file.ics",
            auth_context=auth_context,
        )
    )

    assert response.status_code == 501
    assert receive_calls == 0
