import logging
import re
from html import escape as escape_xml_text
from unicodedata import category as unicode_category
from urllib.parse import unquote_to_bytes

from defusedxml import ElementTree as DefusedElementTree
from defusedxml.common import DefusedXmlException
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
_DAV_RAW_PATH_MAX_OCTETS = 8192
_DAV_DECODED_PATH_MAX_CHARACTERS = 8192
_DAV_PROPFIND_BODY_MAX_OCTETS = 8192
_DAV_PROJECT_COLLECTION_MEMBER_LIMIT = 256
_XML_SPACE_CHARACTERS = frozenset(" \t\r\n")
_DAV_PROPFIND_DIRECTIVE_TAGS = frozenset(
    {
        "{DAV:}allprop",
        "{DAV:}include",
        "{DAV:}prop",
        "{DAV:}propname",
    }
)


def _validate_dav_raw_request_path(request: Request, decoded_path: str) -> None:
    """Validate wire encoding before trusting the framework-decoded DAV path."""
    raw_path = request.scope.get("raw_path")
    if raw_path is None:
        if len(decoded_path) > _DAV_DECODED_PATH_MAX_CHARACTERS:
            raise HTTPException(
                status_code=414,
                detail="DAV decoded path exceeds 8192 characters",
            )
        if "%" in decoded_path:
            raise HTTPException(
                status_code=400,
                detail="DAV raw path required for percent-bearing path",
            )
        return
    if not isinstance(raw_path, bytes):
        raise HTTPException(status_code=400, detail="DAV raw path is unavailable")
    if len(raw_path) > _DAV_RAW_PATH_MAX_OCTETS:
        raise HTTPException(
            status_code=414,
            detail="DAV raw path exceeds 8192 octets",
        )
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
    source_has_leading_slash = path.startswith("/")
    normalized_path = path.replace("\\", "/")
    if "\ufffd" in normalized_path or any(
        0xD800 <= ord(character) <= 0xDFFF for character in normalized_path
    ):
        raise HTTPException(status_code=400, detail="DAV path contains invalid Unicode")
    if any(unicode_category(character) == "Cc" for character in normalized_path):
        raise HTTPException(status_code=400, detail="DAV path contains control characters")
    if normalized_path.startswith("/") and not source_has_leading_slash:
        raise HTTPException(
            status_code=400,
            detail="DAV path contains ambiguous empty segments",
        )
    path_segments = normalized_path.split("/")
    has_traversal_segment = any(segment in {".", ".."} for segment in path_segments)
    if "//" in normalized_path and not has_traversal_segment:
        raise HTTPException(
            status_code=400,
            detail="DAV path contains ambiguous empty segments",
        )
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


def _dav_finite_depth_error_response() -> Response:
    return Response(
        content=(
            '<?xml version="1.0" encoding="utf-8" ?>\n'
            '<D:error xmlns:D="DAV:"><D:propfind-finite-depth/></D:error>'
        ),
        media_type="application/xml",
        status_code=403,
    )


def _dav_project_member_limit_error_response() -> Response:
    return Response(
        content=(
            '<?xml version="1.0" encoding="utf-8" ?>\n'
            '<D:error xmlns:D="DAV:" xmlns:N="urn:naruon:dav">'
            '<N:project-member-limit/></D:error>'
        ),
        media_type="application/xml",
        status_code=403,
    )


def _dav_depth(request: Request) -> str:
    depth_header = request.headers.get("Depth")
    if depth_header is None:
        return "infinity"
    depth = depth_header.strip().lower()
    if depth not in {"0", "1", "infinity"}:
        raise HTTPException(
            status_code=400,
            detail="DAV Depth must be 0, 1, or infinity",
        )
    return depth


def _has_non_xml_space_content(text: str | None) -> bool:
    """Return whether element-only content contains characters outside XML S."""
    return bool(text) and any(character not in _XML_SPACE_CHARACTERS for character in text)


def _validate_dav_empty_directive(element, *, directive_name: str) -> None:
    """Validate EMPTY directive text while ignoring RFC-permitted extension children."""
    extension_children = list(element)
    if _has_non_xml_space_content(element.text) or any(
        _has_non_xml_space_content(extension_child.tail)
        for extension_child in extension_children
    ):
        raise HTTPException(
            status_code=400,
            detail=f"DAV {directive_name} directive must not contain text",
        )


def _validate_dav_property_name_container(element, *, directive_name: str) -> None:
    """Reject text, mixed content, or property values in name-only selectors."""
    property_names = list(element)
    if _has_non_xml_space_content(element.text) or any(
        _has_non_xml_space_content(property_name.tail)
        for property_name in property_names
    ):
        raise HTTPException(
            status_code=400,
            detail=f"DAV {directive_name} directive must not contain text",
        )
    if any(
        list(property_name) or _has_non_xml_space_content(property_name.text)
        for property_name in property_names
    ):
        raise HTTPException(
            status_code=400,
            detail=f"DAV {directive_name} directive must contain property names only",
        )


async def _validate_dav_propfind_body(request: Request) -> None:
    """Validate the bounded PROPFIND body semantics this discovery slice supports."""
    request_body = bytearray()
    async for body_chunk in request.stream():
        if not body_chunk:
            continue
        if len(request_body) + len(body_chunk) > _DAV_PROPFIND_BODY_MAX_OCTETS:
            raise HTTPException(
                status_code=413,
                detail="DAV PROPFIND body exceeds 8192 octets",
            )
        request_body.extend(body_chunk)

    if not request_body:
        return

    try:
        propfind_element = DefusedElementTree.fromstring(bytes(request_body))
    except (DefusedXmlException, DefusedElementTree.ParseError) as exc:
        raise HTTPException(
            status_code=400,
            detail="DAV PROPFIND body must be well-formed XML",
        ) from exc

    if propfind_element.tag != "{DAV:}propfind":
        raise HTTPException(
            status_code=400,
            detail="DAV PROPFIND body must contain DAV:propfind",
        )

    all_children = list(propfind_element)
    if _has_non_xml_space_content(propfind_element.text) or any(
        _has_non_xml_space_content(child.tail) for child in all_children
    ):
        raise HTTPException(
            status_code=400,
            detail="DAV PROPFIND body must use element-only directive content",
        )

    directives = [
        child for child in all_children if child.tag in _DAV_PROPFIND_DIRECTIVE_TAGS
    ]

    if len(directives) == 1 and directives[0].tag == "{DAV:}allprop":
        _validate_dav_empty_directive(directives[0], directive_name="allprop")
        return

    if len(directives) == 2 and {element.tag for element in directives} == {
        "{DAV:}allprop",
        "{DAV:}include",
    }:
        allprop_element = next(
            element for element in directives if element.tag == "{DAV:}allprop"
        )
        include_element = next(
            element for element in directives if element.tag == "{DAV:}include"
        )
        _validate_dav_empty_directive(allprop_element, directive_name="allprop")
        _validate_dav_property_name_container(
            include_element,
            directive_name="include",
        )
        raise HTTPException(
            status_code=501,
            detail="DAV allprop include semantics are not implemented",
        )

    if len(directives) == 1 and directives[0].tag == "{DAV:}propname":
        _validate_dav_empty_directive(directives[0], directive_name="propname")
        raise HTTPException(
            status_code=501,
            detail="DAV propname PROPFIND semantics are not implemented",
        )

    if len(directives) == 1 and directives[0].tag == "{DAV:}prop":
        _validate_dav_property_name_container(
            directives[0],
            directive_name="prop",
        )
        raise HTTPException(
            status_code=501,
            detail="DAV selected-property PROPFIND semantics are not implemented",
        )

    raise HTTPException(
        status_code=400,
        detail="DAV PROPFIND body has invalid directive structure",
    )


def _project_folder_response(path_owner_user_id: str, folder: dict) -> str:
    folder_uid = str(folder["folder_uid"])
    project_name = str(folder["project_name"])
    return _dav_response_xml(
        href=f"/api/dav/{path_owner_user_id}/projects/{folder_uid}/",
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
    if depth == "infinity":
        return _dav_finite_depth_error_response()

    folder_uid = segments[2] if len(segments) == 3 else None
    if len(segments) > 3:
        raise HTTPException(status_code=404, detail="DAV project folder not found")

    addressed_collection_response = _dav_response_xml(
        href=f"/api/dav/{path_owner_user_id}/projects/",
        display_name="projects",
        is_collection=True,
    )
    if folder_uid is None and depth == "0":
        return _dav_xml_response([addressed_collection_response])

    if folder_uid is None:
        folders = await webdav_service.get_project_folders_from_db(
            db,
            auth_context.user_id,
            auth_context.organization_id,
            max_results=_DAV_PROJECT_COLLECTION_MEMBER_LIMIT + 1,
        )
        if len(folders) > _DAV_PROJECT_COLLECTION_MEMBER_LIMIT:
            return _dav_project_member_limit_error_response()
        return _dav_xml_response(
            [
                addressed_collection_response,
                *[
                    _project_folder_response(path_owner_user_id, folder)
                    for folder in folders
                ],
            ]
        )

    folders = await webdav_service.get_project_folders_from_db(
        db,
        auth_context.user_id,
        auth_context.organization_id,
        folder_uid=folder_uid,
    )
    if folders:
        if depth == "1":
            raise HTTPException(
                status_code=501,
                detail="DAV project collection member enumeration is not implemented",
            )
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
    if path.startswith("/"):
        raise HTTPException(
            status_code=400,
            detail="DAV path contains ambiguous empty segments",
        )
    canonical_path = _normalize_dav_authorization_path(path)
    _ensure_dav_owner_scope(canonical_path, auth_context)
    safe_path = repr(canonical_path)[1:-1]
    logger.info("DAV Request: %s /%s", request.method, safe_path)

    if request.method == "OPTIONS":
        return Response(status_code=200, headers={"Allow": "OPTIONS, PROPFIND"})

    if request.method == "PROPFIND":
        await _validate_dav_propfind_body(request)
        return await _handle_project_propfind(
            request=request,
            path=canonical_path,
            auth_context=auth_context,
            db=db,
        )

    if request.method == "PUT":
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
