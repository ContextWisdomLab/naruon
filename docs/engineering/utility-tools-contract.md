# Utility Tools Contract

The tools console is an interactive boundary: it submits the values entered by
the user for each registered parameter. Empty string values are intentional;
the console does not submit a canned sample value.
Successful executions display the returned `result`; failure responses display
their error message and a stable `error_code` for client branching.

When the catalog is refreshed, only values whose parameter names and types
still match the refreshed schema are retained. Removed parameters and values
incompatible with a changed type are replaced with that type's default.

The five text utilities enforce a 100,000-character input limit at the shared
tool-parameter validation boundary. The JSON formatter preserves the original
lexical form of valid JSON numbers through the public `json.loads` hooks,
canonicalizes equivalent JSON string escapes, and rejects duplicate object
names and non-standard numeric constants. The URL decoder
rejects incomplete or non-hexadecimal percent escapes and percent-encoded byte
sequences that are not valid UTF-8 instead of silently preserving or replacing
them.

## Standards and research basis

| Contract decision | Basis and applicability |
|---|---|
| URL encoding and decoding use the URI percent-encoding model | RFC 3986 defines a percent-encoded octet as `%` followed by exactly two hexadecimal digits. The encoder therefore encodes all non-unreserved input, while the decoder rejects malformed escapes and malformed UTF-8. Python documents `unquote()` as replacing `%xx` escapes and warns that its parsing helpers do not validate inputs, so the API boundary validates the escape grammar first. |
| JSON numbers are not converted through binary floating point | RFC 8259 defines JSON number syntax but does not require a binary floating-point representation. Retaining the parsed token makes formatting whitespace-only for long decimals, large exponents, integers, and nested values. |
| Duplicate JSON names are rejected | RFC 8259 recommends unique object names and notes that implementations differ when names are repeated. Rejecting duplicates is the deterministic, loss-avoiding contract for this formatter. |
| Utility inputs have explicit length bounds | OWASP recommends allowlist validation and length limits at trust boundaries. The shared 100,000-character ceiling bounds memory amplification from encoding, escaping, and pretty-printing. |

## References (APA 7)

Bray, T. (2017). *The JavaScript Object Notation (JSON) data interchange
format* (RFC 8259). Internet Engineering Task Force.
https://www.rfc-editor.org/rfc/rfc8259

Internet Engineering Task Force. (2005). *Uniform Resource Identifier (URI):
Generic syntax* (RFC 3986). https://www.rfc-editor.org/rfc/rfc3986

Python Software Foundation. (2026). *urllib.parse — Parse URLs into
components*. https://docs.python.org/3/library/urllib.parse.html

OWASP Foundation. (n.d.). *Input validation cheat sheet*. Retrieved August 30,
2026, from
https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html

## Verification commands

```text
cd backend && DISABLE_BACKGROUND_WORKERS=1 PYTHONWARNINGS=error uv run pytest -q tests/test_tools_api.py
corepack pnpm@11.5.3 --dir frontend exec vitest run
corepack pnpm@11.5.3 --dir frontend exec playwright test tests/e2e/dashboard-branding.spec.ts -g "submits edited utility-console parameters" --project=desktop
```
