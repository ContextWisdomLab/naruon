# Email authentication — XOAUTH2 delimiter integrity

This note grounds Naruon's SASL XOAUTH2 payload construction at
`backend/services/email_client.py` and the hostile-input regression in
`backend/tests/test_email_client.py`.

## Protocol boundary

RFC 7628 defines OAuth SASL key/value fields as being separated by the octet
`%x01` (Control-A). Google's Gmail XOAUTH2 documentation uses the same wire
shape for the initial client response: one `user` field, one
`auth=Bearer ...` field, and a final empty field, each separated by Control-A.
The delimiter is therefore protocol structure, not ordinary caller-controlled
field data.

Naruon's helper previously interpolated the supplied user identity and access
token into that attribute stream before base64 encoding. A Control-A embedded
inside either value created an additional protocol field boundary. Base64 does
not remove that ambiguity; it only encodes the already-constructed octet
sequence.

## Decision

`generate_oauth2_string()` rejects `\x01` in either the user identity or access
token before the SASL response is constructed. The ordinary response format is
unchanged. The function does not log credentials, repair malformed values,
percent-encode the delimiter, introduce a fallback authentication mechanism, or
broaden the allowed IMAP/SMTP destinations.

The regression corpus covers delimiter injection through both caller-controlled
fields and preserves the existing valid-payload test. This is a structural
protocol validation rule rather than a keyword/security-score heuristic.

## Claim boundary

This change prevents caller data from introducing extra XOAUTH2 field
separators at this construction boundary. It does not by itself claim complete
OAuth, SASL, Gmail, IMAP, or SMTP security; token issuance, audience/scope,
transport security, server policy, credential storage, TLS identity, egress
allowlisting, and provider behavior remain separate controls.

## References (APA 7)

- Mills, W., Showalter, T., & Tschofenig, H. (2015). *A set of Simple
  Authentication and Security Layer (SASL) mechanisms for OAuth* (RFC 7628).
  RFC Editor. https://www.rfc-editor.org/rfc/rfc7628.html
- Google. (n.d.). *OAuth 2.0 mechanism*. Google Workspace. Retrieved August 14,
  2026, from https://developers.google.com/workspace/gmail/imap/xoauth2-protocol

## Verification boundary

The branch is not merge-ready merely because this note and the narrow fix
exist. Current-head repository CI, security, coverage, independent review, and
protected-branch gates remain authoritative.
