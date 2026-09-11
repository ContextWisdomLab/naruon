# JSON formatter strict-validation doctoring

## Scope

Naruon exposes `json_formatter` as a workspace utility that accepts one JSON text, validates it, and returns the same data serialized with two-space indentation. The tool preserves non-ASCII text with `ensure_ascii=False` and applies the existing `ANALYSIS_TEXT_MAX_CHARS` input ceiling. It is a deterministic utility; it does not invoke an LLM or infer semantics.

## Finding

The generated implementation used Python's default `json.loads()` / `json.dumps()` behavior. Python deliberately accepts the non-standard constants `NaN`, `Infinity`, and `-Infinity` unless `parse_constant` rejects them, and its encoder emits those constants when `allow_nan=True` (the default). RFC 8259 section 6 does not permit Infinity or NaN in the JSON number grammar. A formatter advertised as a JSON validator therefore cannot accept those inputs and return text that is outside the interoperable JSON grammar.

The generated feature was also followed by dependency/security commits that eventually removed the feature itself while leaving only frontend dependency changes in PR #1659. Those dependency files belong to canonical owner #1623. Ordinary adoption commit `66439fc025ded2bc185d4a19d70bb6c6bed2a3c8` preserves the generated history as first-parent provenance while adopting exact #1623 `17a7618eda2b212b691f08fa936e042b34258fc9` and its tree. No dependency source is owned by this product lane after that point.

## RED and causal fix

Source-order RED `1b663b12f216ca3a5e201d9aee15da1ce1308065` restores the formatter on the canonical parent tree and adds focused tests for:

- registry invocation and two-space formatting;
- Korean/Unicode text preservation;
- malformed JSON syntax;
- the existing input-size ceiling;
- rejection of `NaN`, `Infinity`, and `-Infinity`.

The predecessor parser accepts the three non-finite literals, so those cases define the defect rather than a preferred implementation.

Causal fix `a8d4a0f157f1d540980adc933cc6038395511dbe` supplies `parse_constant` to reject Python's non-standard constants and sets `allow_nan=False` on serialization as a second fail-closed boundary. The public tool error remains deterministic (`Invalid JSON string`) instead of exposing parser-location details. No arbitrary nesting, token, number-range, retry, or timeout limit is introduced by this repair.

## Rejected alternatives

- Treating Python's permissive defaults as valid JSON was rejected because it contradicts RFC 8259 interoperability syntax.
- String-searching for `NaN` or `Infinity` was rejected because it would confuse string values or member names with numeric tokens.
- Moving the frontend security bump into this PR was rejected because #1623 owns manifest/lock/security-floor truth.
- Reformatting keys or normalizing Unicode was rejected because the formatter should change presentation, not user data semantics.

## Acceptance boundary

The focused contract is GREEN only when the unchanged exact head executes the tests in `backend/tests/test_json_formatter_tool.py` together with the repository's normal backend checks. A local parser probe can validate the Python boundary but is not a substitute for exact-head CI. Stacked-PR workflow evidence must remain bound to the actual repository, PR, base SHA, and head SHA; predecessor or pre-retarget receipts do not transfer.

This work does not claim complete JSON canonicalization. It preserves object insertion order and numeric values as parsed by Python; canonical JSON, duplicate-member rejection, arbitrary-precision normalization, or cryptographic signing are separate contracts.

## Traceability

- Product source: `backend/api/tools.py`
- Focused regression: `backend/tests/test_json_formatter_tool.py`
- PR: `ContextualWisdomLab/naruon#1659`
- Canonical dependency-security parent: `ContextualWisdomLab/naruon#1623`
- Generated feature provenance: `d033158e77a40f6957cfd4f6f6cc0d8f18819f27`
- Generated feature removal: `02b961f70d1ca75b263f04aef853633609d9380d`
- Parent adoption: `66439fc025ded2bc185d4a19d70bb6c6bed2a3c8`
- Strict JSON RED: `1b663b12f216ca3a5e201d9aee15da1ce1308065`
- Strict JSON fix: `a8d4a0f157f1d540980adc933cc6038395511dbe`

## References

Bray, T. (2017). *The JavaScript Object Notation (JSON) Data Interchange Format* (RFC 8259; STD 90). Internet Engineering Task Force. https://doi.org/10.17487/RFC8259

Python Software Foundation. (2026). *json — JSON encoder and decoder (Python 3.14.7 documentation)*. https://docs.python.org/3.14/library/json.html
