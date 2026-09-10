import logging
import re
from html import escape as escape_xml_text
from unicodedata import category as unicode_category
from urllib.parse import unquote_to_bytes

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import AuthContext, get_auth_context
from db.session import get_db
from services.webdav_service import webdav_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dav", tags=["dav"])


_INVALID_RAW_PERCENT_ESCAPE = re.compile(br"%(?![0-9A-Fa-f]{2})")
_SECOND_PASS_PERCENT_ESCAPE = re.compile(br"%[0-9A-Fa-f]{2}")
_ENCODED_CONTROL_CHARACTER = re.compile(br"%(?:0[0-9A-Fa-f]|1[0-9A-Fa-f]|7[Ff])")


def _validate_dav_raw_request_path(request: Request, decoded_path: str) -> None:
    """Validate wire encoding before trusting the framework-decoded DAV path."""
    raw_path = request.scope.get("raw_path")
    if raw_path is None:
        if "%" in decoded_path:
            raise HTTPException(
                status_code=400,
                detail="DAV raw path required for percent-bearing path",
            )
        return
    if not isinstance(raw_path, bytes):
        raise HTTPException(status_code=400, detail="DAV raw path is unavailable")
    if any(byte < 0x20 or byte == 0x7F for byte in raw_path):
        raise HTTPException(status_code=400, detail="DAV path contains control characters")
    if _INVALID_RAW_PERCENT_ESCAPE.search(raw_path):
        raise HTTPException(
            status_code=400, detail="DAV path contains invalid percent encoding"
        )
    if _ENCODED_CONTROL_CHARACTER.search(raw_path):
        raise HTTPException(status_code=400, detail="DAV path contains control characters")
    first_wire_decode = unquote_to_bytes(raw_path)
    if _SECOND_PASS_PERCENT_ESCAPE.search(first_wire_decode):
        raise HTTPException(
            status_code=400, detail="DAV path contains nested percent encoding"
        )


def _normalize_dav_authorization_path(path: str) -> str:
    """Normalize the path value after ASGI routing has already decoded the target."""
    normalized_path = path.replace("\\", "/")
    if "\ufffd" in normalized_path or any(
        0xD800 <= ord(character) <= 0xDFFF for character in normalized_path
    ):
        raise HTTPException(status_code=400, detail="DAV path contains invalid Unicode")
    if any(unicode_category(character) == "Cc" for character in normalized_path):
        raise HTTPException(status_code=400, detail="DAV path contains control characters")
    return normalized_path


def _dav_path_owner_user_id(path: str) -> str | None:
    path = _normalize_dav_authorization_path(path)
    if any(segment in {".", ".."} for segment in path.split("/")):
        return None
    normalized_path = path.strip("/")
    if not normalized_path:
        return None
    owner_user_id, _, _ = normalized_path.partition("/")
    return owner_user_id or None


def _ensure_dav_owner_scope(path: str, auth_context: AuthContext) -> None:
    owner_user_id = _dav_path_owner_user_id(path)
    if owner_user_id is None:
        raise HTTPException(
            status_code=403,
            detail="DAV path must include an owner user",
        )
    if owner_user_id == auth_context.user_id:
        return
    raise HTTPException(
        status_code=403,
        detail="DAV path belongs to a different user",
    )


def _dav_path_segments(path: str) -> list[str]:
    return [segment for segment in path.strip("/").split("/") if segment]


def _dav_multistatus_xml(responses: list[str]) -> str:
    response_xml = "\n".join(responses)
    if response_xml:
        response_xml = f"\n{response_xml}\n"
    return f"""<?xml version="1.0" encoding="utf-8" ?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">{response_xml}</D:multistatus>"""


def _dav_response_xml(
    *,
    href: str,
    display_name: str,
    is_collection: bool = True,
) -> str:
    resourcetype = "<D:collection/>" if is_collection else ""
    escaped_href = escape_xml_text(href)
    escaped_display_name = escape_xml_text(display_name)
    return f"""  <D:response>
    <D:href>{escaped_href}</D:href>
    <D:propstat>
      <D:prop>
        <D:resourcetype>{resourcetype}</D:resourcetype>
        <D:displayname>{escaped_display_name}</D:displayname>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>"""


def _dav_xml_response(responses: list[str]) -> Response:
    return Response(
        content=_dav_multistatus_xml(responses),
        media_type="application/xml",
        status_code=207,
    )


def _dav_depth(request: Request) -> str:
    depth = request.headers.get("Depth", "1").strip().lower()
    if depth == "0":
        return "0"
    return "1"


def _project_folder_response(path_owner_user_id: str, folder: dict) -> str:
    folder_uid = str(folder["folder_uid"])
    project_name = str(folder["project_name"])
    return _dav_response_xml(
        href=f"/api/dav/{path_owner_user_id}/projects/{folder_uid}",
        display_name=project_name,
        is_collection=True,
    )


async def _handle_project_propfind(
    *,
    request: Request,
    path: str,
    auth_context: AuthContext,
    db: AsyncSession,
) -> Response:
    segments = _dav_path_segments(path)
    if len(segments) < 2 or segments[1] != "projects":
        raise HTTPException(status_code=404, detail="DAV collection not found")

    path_owner_user_id = segments[0]
    depth = _dav_depth(request)
    folder_uid = segments[2] if len(segments) == 3 else None
    if len(segments) > 3:
        raise HTTPException(status_code=404, detail="DAV project folder not found")

    if folder_uid is None and depth == "0":
        return _dav_xml_response(
            [
                _dav_response_xml(
                    href=f"/api/dav/{path_owner_user_id}/projects/",
                    display_name="projects",
                    is_collection=True,
                )
            ]
        )

    folders = await webdav_service.get_project_folders_from_db(
        db,
        auth_context.user_id,
        auth_context.organization_id,
        folder_uid=folder_uid,
    )

    if folder_uid is None:
        return _dav_xml_response(
            [_project_folder_response(path_owner_user_id, folder) for folder in folders]
        )

    if folders:
        return _dav_xml_response(
            [_project_folder_response(path_owner_user_id, folder) for folder in folders]
        )

    raise HTTPException(status_code=404, detail="DAV project folder not found")


@router.api_route(
    "/{path:path}",
    methods=["PROPFIND", "REPORT", "MKCOL", "GET", "PUT", "DELETE", "OPTIONS"],
)
async def dav_handler(
    request: Request,
    path: str,
    auth_context: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Route the authenticated DAV surface that is implemented for this slice.

    Collection discovery is served from the server-side project registry.
    Provider-backed writeback stays fail-closed until source capability and
    ETag/If-Match enforcement are available through signed writeback intents.
    """
    _validate_dav_raw_request_path(request, path)
    _ensure_dav_owner_scope(path, auth_context)
    safe_path = repr(path)[1:-1]
    logger.info("DAV Request: %s /%s", request.method, safe_path)

    if request.method == "OPTIONS":
        headers = {
            "DAV": "1, 2, 3, calendar-access, addressbook",
            "Allow": (
                "OPTIONS, GET, HEAD, POST, PUT, DELETE, TRACE, COPY, MOVE, MKCOL, "
                "PROPFIND, PROPPATCH, LOCK, UNLOCK, REPORT"
            ),
        }
        return Response(status_code=200, headers=headers)

    if request.method == "PROPFIND":
        return await _handle_project_propfind(
            request=request,
            path=path,
            auth_context=auth_context,
            db=db,
        )

    if request.method == "PUT":
        body = await request.body()
        safe_path = repr(path)[1:-1]
        logger.info("DAV PUT received %s bytes at /%s", len(body), safe_path)
        logger.warning(
            "DAV PUT rejected at /%s: provider-backed DAV writeback is not "
            "implemented; signed writeback-intent API is required",
            safe_path,
        )
        return Response(
            content=(
                "Provider-backed DAV writeback is not implemented; use signed "
                "writeback-intent APIs until source, capability, and "
                "ETag/If-Match checks are enforced."
            ),
            media_type="text/plain",
            status_code=501,
        )

    logger.warning(
        "DAV %s rejected at /%s: method is not implemented for the "
        "provider-backed DAV gateway",
        request.method,
        safe_path,
    )
    return Response(
        content=(
            "Provider-backed DAV method is not implemented; use supported "
            "PROPFIND/OPTIONS discovery or signed writeback-intent APIs."
        ),
        media_type="text/plain",
        status_code=501,
    )
