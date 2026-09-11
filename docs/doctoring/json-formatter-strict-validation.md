# JSON formatter strict-validation doctoring

## Scope

Naruon exposes `json_formatter` as a workspace utility that accepts one JSON text, validates it, and returns the same data serialized with two-space indentation. The tool preserves non-ASCII text with `ensure_ascii=False` and applies the existing `ANALYSIS_TEXT_MAX_CHARS` input ceiling. It is a deterministic utility; it does not invoke an LLM or infer semantics.

## Findings

The generated implementation used Python's default `json.loads()` / `json.dumps()` behavior. Python deliberately accepts the non-standard constants `NaN`, `Infinity`, and `-Infinity` unless `parse_constant` rejects them, and its encoder emits those constants when `allow_nan=True` (the default). RFC 8259 section 6 does not permit Infinity or NaN in the JSON number grammar. A formatter advertised as a JSON validator therefore cannot accept those inputs and return text that is outside the interoperable JSON grammar.

A later exact-head audit found a second data-integrity boundary. Python's normal object decoding constructs a dictionary and therefore retains only one value when the same decoded member name occurs more than once. RFC 8259 section 4 says object member names SHOULD be unique and warns that receiver behavior is unpredictable when they are not: implementations may keep the last pair, reject the object, or expose every pair. A formatter that silently accepts `{\"id\":1,\"id\":2}` and returns only one `id` value has changed the user's data while presenting the result as validation/formatting. Naruon therefore rejects duplicate decoded member names rather than choosing first-wins or last-wins semantics.

The generated feature was also followed by dependency/security commits that eventually removed the feature itself while leaving only frontend dependency changes in PR #1659. Those dependency files belong to canonical owner #1623. Ordinary adoption commit `66439fc025ded2bc185d4a19d70bb6c6bed2a3c8` preserves the generated history as first-parent provenance while adopting exact #1623 `17a7618eda2b212b691f08fa936e042b34258fc9` and its tree. No dependency source is owned by this product lane after that point.

## RED and causal fixes

Source-order RED `1b663b12f216ca3a5e201d9aee15da1ce1308065` restores the formatter on the canonical parent tree and adds focused tests for registry invocation, two-space formatting, Korean/Unicode preservation, malformed JSON syntax, the existing input-size ceiling, and rejection of `NaN`, `Infinity`, and `-Infinity`. The predecessor parser accepts the three non-finite literals, so those cases define the defect rather than a preferred implementation.

Causal fix `a8d4a0f157f1d540980adc933cc6038395511dbe` supplies `parse_constant` to reject Python's non-standard constants and sets `allow_nan=False` on serialization as a second fail-closed boundary. The public tool error remains deterministic (`Invalid JSON string`) instead of exposing parser-location details.

Source-order duplicate-member RED `83fcf7a81c436f3018886ff56cfaab130bc594ff` adds top-level and nested duplicate-name inputs plus the public `execute_tool` failure envelope. Under the predecessor implementation those inputs are accepted after an earlier member value is silently discarded.

Causal fix `3eb383487b5aed4ffdf48fbd588c2152aea02991` supplies `object_pairs_hook` and constructs each JSON object only after checking every decoded member name for prior occurrence. Because the hook is invoked for every object, the same rule applies to nested objects. Detection happens on decoded string names, so escape-spelling differences that decode to the same name do not evade the contract. The failure is again normalized to `Invalid JSON string` at the public tool boundary.

No arbitrary nesting, token, number-range, retry, or timeout limit is introduced by these repairs.

## Rejected alternatives

- Treating Python's permissive non-finite defaults as valid JSON was rejected because it contradicts RFC 8259 interoperability syntax.
- String-searching for `NaN`, `Infinity`, or duplicate member names was rejected because lexical search cannot distinguish strings from tokens or correctly interpret escaping and nesting.
- Keeping the first or last duplicate object member was rejected because either choice silently discards user input and different JSON implementations make different choices.
- Moving the frontend security bump into this PR was rejected because #1623 owns manifest/lock/security-floor truth.
- Reformatting keys or normalizing Unicode was rejected because the formatter should change presentation, not user data semantics.

## Acceptance boundary

The focused contract is GREEN only when the unchanged exact head executes `backend/tests/test_json_formatter_tool.py` together with the repository's normal backend checks. Acceptance includes malformed syntax, all three non-finite constants, top-level and nested duplicate member names, the public failed-execution envelope, Unicode preservation, and the input-size ceiling. A local parser probe can validate the Python boundary but is not a substitute for exact-head CI. Stacked-PR workflow evidence must remain bound to the actual repository, PR, base SHA, and head SHA; predecessor or pre-retarget receipts do not transfer.

This work does not claim complete JSON canonicalization. It preserves object insertion order for accepted objects and numeric values as parsed by Python; canonical JSON, arbitrary-precision numeric normalization, schema validation, or cryptographic signing remain separate contracts.

## Traceability

- Product source: `backend/api/tools.py`
- Focused regression: `backend/tests/test_json_formatter_tool.py`
- PR: `ContextualWisdomLab/naruon#1659`
- Canonical dependency-security parent: `ContextualWisdomLab/naruon#1623`
- Generated feature provenance: `d033158e77a40f6957cfd4f6f6cc0d8f18819f27`
- Generated feature removal: `02b961f70d1ca75b263f04aef853633609d9380d`
- Parent adoption: `66439fc025ded2bc185d4a19d70bb6c6bed2a3c8`
- Strict-number RED/fix: `1b663b12f216ca3a5e201d9aee15da1ce1308065` → `a8d4a0f157f1d540980adc933cc6038395511dbe`
- Duplicate-member RED/fix: `83fcf7a81c436f3018886ff56cfaab130bc594ff` → `3eb383487b5aed4ffdf48fbd588c2152aea02991`

## References

Bray, T. (2017). *The JavaScript Object Notation (JSON) Data Interchange Format* (RFC 8259; STD 90). Internet Engineering Task Force. https://doi.org/10.17487/RFC8259

Python Software Foundation. (2026). *json — JSON encoder and decoder (Python 3.14.7 documentation)*. https://docs.python.org/3.14/library/json.html
