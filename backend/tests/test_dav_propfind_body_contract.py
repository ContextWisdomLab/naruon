"""Executable contract for bounded PROPFIND request-body semantics."""

import defusedxml.ElementTree as ET
from fastapi.testclient import TestClient

from main import app

AUTH_HEADERS = {
    "X-User-Id": "user123",
    "X-User-Role": "organization_admin",
    "X-Organization-Id": "org-acme",
    "Depth": "0",
    "Content-Type": "application/xml; charset=utf-8",
}


def _propfind_request(body: bytes):
    with TestClient(app) as client:
        return client.request(
            "PROPFIND",
            "/dav/user123/projects/",
            headers=AUTH_HEADERS,
            content=body,
        )


def test_empty_propfind_body_keeps_supported_discovery_profile(
    dev_auth_dependency_overrides,
) -> None:
    """An empty body remains equivalent to the supported allprop profile."""

    response = _propfind_request(b"")

    assert response.status_code == 207
    root = ET.fromstring(response.text)
    assert root.findtext(".//{DAV:}displayname") == "projects"
    assert root.find(".//{DAV:}resourcetype/{DAV:}collection") is not None


def test_explicit_allprop_keeps_supported_discovery_profile(
    dev_auth_dependency_overrides,
) -> None:
    """Explicit allprop uses the same bounded property profile as an empty body."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:"><D:allprop/></D:propfind>'
    )

    assert response.status_code == 207
    root = ET.fromstring(response.text)
    assert root.findtext(".//{DAV:}displayname") == "projects"
    assert root.find(".//{DAV:}resourcetype/{DAV:}collection") is not None


def test_propname_is_not_silently_coerced_to_allprop(
    dev_auth_dependency_overrides,
) -> None:
    """Unsupported propname semantics must fail instead of returning property values."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:"><D:propname/></D:propfind>'
    )

    assert response.status_code == 501


def test_named_prop_is_not_silently_coerced_to_allprop(
    dev_auth_dependency_overrides,
) -> None:
    """Unsupported named-property selection must not return the allprop profile."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:"><D:prop><D:displayname/></D:prop></D:propfind>'
    )

    assert response.status_code == 501


def test_named_prop_value_is_invalid_before_mode_refusal(
    dev_auth_dependency_overrides,
) -> None:
    """A prop selector may name properties but must not carry property values."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:"><D:prop><D:displayname>unexpected'
        b'</D:displayname></D:prop></D:propfind>'
    )

    assert response.status_code == 400


def test_allprop_include_is_recognized_but_not_silently_ignored(
    dev_auth_dependency_overrides,
) -> None:
    """A valid allprop/include request must fail until include semantics exist."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:"><D:allprop/><D:include>'
        b'<D:getetag/></D:include></D:propfind>'
    )

    assert response.status_code == 501


def test_include_property_value_is_invalid_before_mode_refusal(
    dev_auth_dependency_overrides,
) -> None:
    """An include selector names properties; nested property values are invalid."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:"><D:allprop/><D:include>'
        b'<D:getetag>unexpected</D:getetag></D:include></D:propfind>'
    )

    assert response.status_code == 400


def test_include_mixed_text_is_invalid_before_mode_refusal(
    dev_auth_dependency_overrides,
) -> None:
    """DAV:include cannot contain text or mixed content."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:"><D:allprop/><D:include>unexpected'
        b'<D:getetag/></D:include></D:propfind>'
    )

    assert response.status_code == 400


def test_non_empty_allprop_with_include_is_invalid_before_mode_refusal(
    dev_auth_dependency_overrides,
) -> None:
    """DAV:allprop stays EMPTY when paired with a valid include directive."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:"><D:allprop>unexpected</D:allprop>'
        b'<D:include><D:getetag/></D:include></D:propfind>'
    )

    assert response.status_code == 400


def test_propfind_root_text_is_rejected(
    dev_auth_dependency_overrides,
) -> None:
    """The element-only propfind grammar must reject non-whitespace root text."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:">unexpected<D:allprop/></D:propfind>'
    )

    assert response.status_code == 400


def test_unicode_spaces_are_not_silently_treated_as_xml_whitespace(
    dev_auth_dependency_overrides,
) -> None:
    """Only XML S characters may separate element-only PROPFIND grammar."""

    bodies = [
        '<D:propfind xmlns:D="DAV:">\u00a0<D:allprop/></D:propfind>',
        '<D:propfind xmlns:D="DAV:"><D:allprop>\u00a0</D:allprop></D:propfind>',
        '<D:propfind xmlns:D="DAV:"><D:allprop/><D:include>\u00a0'
        '<D:getetag/></D:include></D:propfind>',
    ]

    for body in bodies:
        response = _propfind_request(body.encode("utf-8"))
        assert response.status_code == 400


def test_propfind_child_tail_text_is_rejected(
    dev_auth_dependency_overrides,
) -> None:
    """The element-only propfind grammar must reject non-whitespace child tails."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:"><D:allprop/>unexpected</D:propfind>'
    )

    assert response.status_code == 400


def test_non_empty_propname_is_rejected_as_invalid_grammar(
    dev_auth_dependency_overrides,
) -> None:
    """DAV:propname is EMPTY and must fail before unsupported-mode classification."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:"><D:propname>unexpected</D:propname>'
        b'</D:propfind>'
    )

    assert response.status_code == 400


def test_malformed_propfind_xml_is_rejected(
    dev_auth_dependency_overrides,
) -> None:
    """Malformed XML must not be ignored and converted into a successful discovery."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:"><D:allprop></D:propfind>'
    )

    assert response.status_code == 400


def test_non_propfind_root_is_rejected(
    dev_auth_dependency_overrides,
) -> None:
    """A well-formed XML body with the wrong root is not a PROPFIND request body."""

    response = _propfind_request(b'<D:allprop xmlns:D="DAV:"/>')

    assert response.status_code == 400


def test_non_empty_allprop_directive_is_rejected(
    dev_auth_dependency_overrides,
) -> None:
    """The allprop directive is an empty element in the RFC grammar."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:"><D:allprop><D:displayname/>'
        b'</D:allprop></D:propfind>'
    )

    assert response.status_code == 400


def test_conflicting_propfind_directives_are_rejected(
    dev_auth_dependency_overrides,
) -> None:
    """A body cannot ask for both allprop and propname semantics."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:"><D:allprop/><D:propname/></D:propfind>'
    )

    assert response.status_code == 400


def test_propfind_external_entity_is_rejected(
    dev_auth_dependency_overrides,
) -> None:
    """PROPFIND XML parsing must not resolve attacker-controlled external entities."""

    response = _propfind_request(
        b'<!DOCTYPE propfind [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        b'<D:propfind xmlns:D="DAV:"><D:prop><D:displayname>&xxe;'
        b'</D:displayname></D:prop></D:propfind>'
    )

    assert response.status_code == 400


def test_propfind_body_work_is_bounded(
    dev_auth_dependency_overrides,
) -> None:
    """A request body above the Naruon discovery ceiling must fail before XML parsing."""

    response = _propfind_request(b"x" * 8193)

    assert response.status_code == 413


def test_unrecognized_propfind_extension_element_is_ignored(
    dev_auth_dependency_overrides,
) -> None:
    """Unexpected command extensions must be processed as if they were absent."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:" xmlns:X="urn:example:dav-ext">'
        b'<X:trace><X:nested/></X:trace><D:allprop/></D:propfind>'
    )

    assert response.status_code == 207


def test_allprop_extension_child_is_ignored(
    dev_auth_dependency_overrides,
) -> None:
    """RFC extension children do not make DAV:allprop non-empty for processing."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:" xmlns:X="urn:example:dav-ext">'
        b'<D:allprop><X:trace><X:nested/></X:trace></D:allprop></D:propfind>'
    )

    assert response.status_code == 207


def test_allprop_include_order_is_not_semantic(
    dev_auth_dependency_overrides,
) -> None:
    """Element order does not change recognition of allprop/include semantics."""

    response = _propfind_request(
        b'<D:propfind xmlns:D="DAV:"><D:include><D:getetag/></D:include>'
        b'<D:allprop/></D:propfind>'
    )

    assert response.status_code == 501
