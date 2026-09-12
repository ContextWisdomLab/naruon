import ipaddress
import socket
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Literal
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import httpx

from runner.utils.dispatch import dispatch_error


_MAX_TARGET_PATH_LENGTH = 4096
_MAX_URL_DECODE_ROUNDS = 4


@dataclass(frozen=True)
class LocalDavSourceConfig:
    source_id: str
    protocol: Literal["caldav", "webdav", "carddav"]
    base_url: str
    username: str | None = None
    password: str | None = None
    writeback_enabled: bool = False


class LocalDavAdapters:
    def __init__(
        self,
        sources: Iterable[LocalDavSourceConfig],
        *,
        http_client_factory: Callable[[], Any] | None = None,
    ):
        self._sources = {
            source.source_id.strip(): source
            for source in sources
            if source.source_id.strip()
        }
        self._http_client_factory = http_client_factory or self._default_http_client

    async def write_webdav(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._put(
            payload,
            protocol="webdav",
            default_content_type="application/octet-stream",
        )

    async def write_caldav(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._put(
            payload,
            protocol="caldav",
            default_content_type="text/calendar; charset=utf-8",
        )

    async def write_carddav(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._put(
            payload,
            protocol="carddav",
            default_content_type="text/vcard; charset=utf-8",
        )

    def _default_http_client(self):
        return httpx.AsyncClient(follow_redirects=False, timeout=60)

    async def _put(
        self,
        payload: dict[str, Any],
        *,
        protocol: Literal["caldav", "webdav", "carddav"],
        default_content_type: str,
    ) -> dict[str, Any]:
        source = self._source_for_payload(payload, protocol)
        if source is None:
            return dispatch_error("source_not_configured")
        if not source.writeback_enabled:
            return dispatch_error("source_writeback_disabled")

        if_match = self._payload_text(payload, "if_match")
        if if_match is None:
            return dispatch_error("missing_if_match")

        target_path = self._safe_target_path(payload.get("target_path"))
        if target_path is None:
            return dispatch_error("invalid_target_path")

        content = self._payload_content(payload.get("content"))
        if content is None:
            return dispatch_error("invalid_payload")

        try:
            target_url = self._target_url(source.base_url, target_path)
        except ValueError as exc:
            return dispatch_error(str(exc))

        content_type = (
            self._payload_text(payload, "content_type") or default_content_type
        )
        headers = {"Content-Type": content_type, "If-Match": if_match}
        auth = (
            (source.username, source.password or "")
            if source.username is not None
            else None
        )

        try:
            async with self._http_client_factory() as client:
                response = await client.put(
                    target_url,
                    content=content,
                    headers=headers,
                    auth=auth,
                )
        except httpx.HTTPError:
            return dispatch_error("provider_request_failed")

        return self._result_from_response(response)

    def _source_for_payload(
        self,
        payload: dict[str, Any],
        protocol: Literal["caldav", "webdav", "carddav"],
    ) -> LocalDavSourceConfig | None:
        source_id = self._payload_text(payload, "source_id")
        if source_id is None:
            return None
        source = self._sources.get(source_id)
        if source is None or source.protocol != protocol:
            return None
        return source

    def _payload_text(self, payload: dict[str, Any], key: str) -> str | None:
        value = payload.get(key)
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    def _payload_content(self, value: Any) -> bytes | None:
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
        return None

    def _safe_target_path(self, raw_path: Any) -> str | None:
        """Return one canonical DAV path or reject encoded traversal/control data."""
        if (
            not isinstance(raw_path, str)
            or not raw_path
            or len(raw_path) > _MAX_TARGET_PATH_LENGTH
        ):
            return None

        decoded_path = raw_path
        try:
            for _ in range(_MAX_URL_DECODE_ROUNDS):
                next_path = unquote(decoded_path, errors="strict")
                if next_path == decoded_path:
                    break
                decoded_path = next_path
            else:
                if unquote(decoded_path, errors="strict") != decoded_path:
                    return None
        except UnicodeDecodeError:
            return None

        if (
            not decoded_path.startswith("/")
            or "\\" in decoded_path
            or "://" in decoded_path
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in decoded_path
            )
        ):
            return None
        segments = [segment for segment in decoded_path.split("/") if segment]
        if not segments or any(segment in {".", ".."} for segment in segments):
            return None
        return "/" + "/".join(
            quote(segment, safe="@:$&'()*+,;=-._~") for segment in segments
        )

    def _target_url(self, base_url: str, target_path: str) -> str:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("invalid_source_url")
        try:
            source_port = parsed.port or 443
        except ValueError as exc:
            raise ValueError("invalid_source_url") from exc
        self._validate_global_source_host(parsed.hostname, source_port)
        base_path = parsed.path.rstrip("/")
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                f"{base_path}{target_path}",
                "",
                "",
            )
        )

    def _validate_global_source_host(self, hostname: str, port: int) -> None:
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            self._validate_global_address(hostname)
            return

        try:
            address_infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValueError("invalid_source_url") from exc
        addresses = {str(address_info[4][0]) for address_info in address_infos}
        if not addresses:
            raise ValueError("invalid_source_url")
        for address in addresses:
            self._validate_global_address(address)

    @staticmethod
    def _validate_global_address(address: str) -> None:
        try:
            ip_address = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ValueError("invalid_source_url") from exc
        if not ip_address.is_global:
            raise ValueError("invalid_source_url")

    def _result_from_response(self, response) -> dict[str, Any]:
        status_code = int(response.status_code)
        if status_code in {200, 201, 204}:
            result: dict[str, Any] = {
                "status": "success",
                "provider_write_executed": True,
                "provider_status": status_code,
            }
            etag = response.headers.get("ETag") or response.headers.get("etag")
            if etag:
                result["etag"] = etag
            return result
        if status_code in {409, 412}:
            return {
                "status": "conflict",
                "error": "provider_conflict",
                "error_code": "provider_conflict",
                "provider_write_executed": False,
                "provider_status": status_code,
            }
        result = dispatch_error("provider_write_failed")
        result["provider_status"] = status_code
        return result
