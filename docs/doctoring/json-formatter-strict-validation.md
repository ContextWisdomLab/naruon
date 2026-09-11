# JSON formatter strict-validation doctoring

## Scope

Naruon exposes `json_formatter` as a workspace utility that accepts one JSON text, validates it, and returns the same data serialized with two-space indentation. The tool preserves non-ASCII text with `ensure_ascii=False` and applies the existing `ANALYSIS_TEXT_MAX_CHARS` input ceiling. It is a deterministic utility; it does not invoke an LLM or infer semantics.

## Findings

The generated implementation used Python's default `json.loads()` / `json.dumps()` behavior. Python deliberately accepts the non-standard constants `NaN`, `Infinity`, and `-Infinity` unless `parse_constant` rejects them, and its encoder emits those constants when `allow_nan=True` (the default). RFC 8259 section 6 does not permit Infinity or NaN in the JSON number grammar. A formatter advertised as a JSON validator therefore cannot accept those inputs and return text that is outside the interoperable JSON grammar.

A later exact-head audit found a second data-integrity boundary. Python's normal object decoding constructs a dictionary and therefore retains only one value when the same decoded member name occurs more than once. RFC 8259 section 4 says object member names SHOULD be unique and warns that receiver behavior is unpredictable when they are not: implementations may keep the last pair, reject the object, or expose every pair. A formatter that silently accepts `{\"id\":1,\"id\":2}` and returns only one `id` value has changed the user's data while presenting the result as validation/formatting. Naruon therefore rejects duplicate decoded member names rather than choosing first-wins or last-wins semantics.

A third exact-head audit found that valid-but-extremely-deep nesting can exceed the Python interpreter's recursion boundary before the existing 100,000-character ceiling is reached. In that case `json.loads()` raises `RecursionError`, while the formatter normalized only `JSONDecodeError` and `ValueError`. Direct invocation therefore leaked a different exception type, and the public `execute_tool` envelope returned the interpreter-specific recursion message instead of the formatter's deterministic `Invalid JSON string` contract. RFC 8259 section 9 explicitly permits implementations to limit maximum nesting depth, and the Python 3.14 JSON documentation states that the module is still subject to Python interpreter limits. This repair does not invent a new numerical nesting cap; it treats the interpreter-enforced boundary as a validation failure and normalizes it at the product boundary.

A fourth exact-head audit found a Unicode interoperability boundary. Python's decoder can materialize escaped unpaired UTF-16 surrogates such as `\ud800` or `\udc00` as Python strings. With `ensure_ascii=False`, `json.dumps()` can then return a Python string that still contains the surrogate even though the string cannot be encoded as strict UTF-8. That lets the formatter appear to succeed inside the handler and fail later at an HTTP or serialization boundary. RFC 8259 section 8.2 explicitly warns that unpaired surrogate values produce unpredictable cross-implementation behavior. The product boundary therefore requires the formatted result to be UTF-8 representable before returning success, while continuing to accept valid surrogate pairs that decode to ordinary Unicode scalar values such as `😀`.

The generated feature was also followed by dependency/security commits that eventually removed the feature itself while leaving only frontend dependency changes in PR #1659. Those dependency files belong to canonical owner #1623. Ordinary adoption commit `66439fc025ded2bc185d4a19d70bb6c6bed2a3c8` preserves the generated history as first-parent provenance while adopting exact #1623 `17a7618eda2b212b691f08fa936e042b34258fc9` and its tree. No dependency source is owned by this product lane after that point.

## RED and causal fixes

Source-order RED `1b663b12f216ca3a5e201d9aee15da1ce1308065` restores the formatter on the canonical parent tree and adds focused tests for registry invocation, two-space formatting, Korean/Unicode preservation, malformed JSON syntax, the existing input-size ceiling, and rejection of `NaN`, `Infinity`, and `-Infinity`. The predecessor parser accepts the three non-finite literals, so those cases define the defect rather than a preferred implementation.

Causal fix `a8d4a0f157f1d540980adc933cc6038395511dbe` supplies `parse_constant` to reject Python's non-standard constants and sets `allow_nan=False` on serialization as a second fail-closed boundary. The public tool error remains deterministic (`Invalid JSON string`) instead of exposing parser-location details.

Source-order duplicate-member RED `83fcf7a81c436f3018886ff56cfaab130bc594ff` adds top-level and nested duplicate-name inputs plus the public `execute_tool` failure envelope. Under the predecessor implementation those inputs are accepted after an earlier member value is silently discarded.

Causal fix `3eb383487b5aed4ffdf48fbd588c2152aea02991` supplies `object_pairs_hook` and constructs each JSON object only after checking every decoded member name for prior occurrence. Because the hook is invoked for every object, the same rule applies to nested objects. Detection happens on decoded string names, so escape-spelling differences that decode to the same name do not evade the contract. Follow-up regression `3351cb2e2e4b56c75457c8b9bc25d08cd845071c` makes that decoded-name boundary executable with `"a"` and `"\u0061"` in the same object. The failure is normalized to `Invalid JSON string` at the public tool boundary.

Source-order recursion-boundary RED `1d92c268196d346aad957b528a261964e9bdcb4d` adds a deeply nested array whose source remains below `ANALYSIS_TEXT_MAX_CHARS`. It requires both direct handler invocation and the public execution envelope to fail with the same deterministic validation message. Under the predecessor implementation the decoder's `RecursionError` escapes the handler contract and the public envelope exposes an interpreter-specific message.

Causal fix `2b76321cc2d354c04d097ec4502777d8fa4838df` includes `RecursionError` in the same formatter validation boundary that already normalizes syntax and strictness failures. The commit briefly carried an unrelated `ToolCreate.category` description edit caused while replacing the source file; repair commit `cfd553e1c0dbce72a91232e00a4080da8d492e0f` restores that unrelated text without changing the recursion fix. The resulting product delta is therefore limited to the intended exception normalization plus its tests and doctoring.

Source-order surrogate RED `80745c3ca25e4194062dadf13d86f6783067643c` adds unpaired high-surrogate, unpaired low-surrogate, and surrogate-member-name inputs at both the direct handler and public `execute_tool` boundary. It also fixes the acceptance side of the contract by requiring the valid pair `\ud83d\ude00` to decode and format as `😀` rather than rejecting all surrogate escapes indiscriminately.

Causal fix `95facece4505db2992e6c69a173a4edb4dbc31dc` keeps `ensure_ascii=False` and validates the already formatted Python string with strict `formatted.encode("utf-8")`. `UnicodeEncodeError` is normalized through the existing `Invalid JSON string` boundary. This rejects values and object-member names that would later fail strict UTF-8 transport without changing ordinary Unicode preservation or valid surrogate-pair behavior.

No arbitrary nesting, token, codepoint, number-range, retry, or timeout limit is introduced by these repairs.

## Rejected alternatives

- Treating Python's permissive non-finite defaults as valid JSON was rejected because it contradicts RFC 8259 interoperability syntax.
- String-searching for `NaN`, `Infinity`, duplicate member names, or surrogate escape spellings was rejected because lexical search cannot distinguish strings from tokens or correctly interpret escaping and nesting.
- Keeping the first or last duplicate object member was rejected because either choice silently discards user input and different JSON implementations make different choices.
- Hard-coding a new nesting depth was rejected because the product already has an input-size ceiling and RFC 8259 allows implementation limits; the minimal defect is inconsistent failure normalization at the actual interpreter boundary.
- Switching the formatter to `ensure_ascii=True` was rejected because it would hide the transport defect by re-escaping all non-ASCII output and would change the existing Unicode-preservation contract.
- Rejecting every surrogate escape lexically was rejected because a valid pair such as `\ud83d\ude00` represents an ordinary Unicode scalar value after decoding and must remain accepted.
- Adding a product-specific Unicode codepoint allowlist was rejected because the defect is UTF-8 representability, not a need to redefine Unicode.
- Moving the frontend security bump into this PR was rejected because #1623 owns manifest/lock/security-floor truth.
- Reformatting keys or normalizing Unicode was rejected because the formatter should change presentation, not user data semantics.

## Acceptance boundary

The focused contract is GREEN only when the unchanged exact head executes `backend/tests/test_json_formatter_tool.py` together with the repository's normal backend checks. Acceptance includes malformed syntax, all three non-finite constants, top-level, nested, and escape-equivalent duplicate member names, recursion-limit nesting below the existing character ceiling, unpaired high/low surrogates in values and object member names, valid surrogate-pair preservation, the public failed-execution envelope, ordinary Unicode preservation, and the input-size ceiling. A local parser probe can validate Python boundary behavior but is not a substitute for exact-head CI. Stacked-PR workflow evidence must remain bound to the actual repository, PR, base SHA, and head SHA; predecessor or pre-retarget receipts do not transfer.

This work does not claim complete JSON canonicalization. It preserves object insertion order for accepted objects and numeric values as parsed by Python; canonical JSON, arbitrary-precision numeric normalization, schema validation, cryptographic signing, and a product-defined nesting-depth SLA remain separate contracts.

## Traceability

- Product source: `backend/api/tools.py`
- Focused regression: `backend/tests/test_json_formatter_tool.py`
- PR: `ContextualWisdomLab/naruon#1659`
- Canonical dependency-security parent: `ContextualWisdomLab/naruon#1623`
- Generated feature provenance: `d033158e77a40f6957cfd4f6f6cc0d8f18819f27`
- Generated feature removal: `02b961f70d1ca75b263f04aef853633609d9380d`
- Parent adoption: `66439fc025ded2bc185d4a19d70bb6c6bed2a3c8`
- Strict-number RED/fix: `1b663b12f216ca3a5e201d9aee15da1ce1308065` → `a8d4a0f157f1d540980adc933cc6038395511dbe`
- Duplicate-member RED/fix/decoded-name edge: `83fcf7a81c436f3018886ff56cfaab130bc594ff` → `3eb383487b5aed4ffdf48fbd588c2152aea02991` → `3351cb2e2e4b56c75457c8b9bc25d08cd845071c`
- Recursion-boundary RED/fix/unrelated-delta repair: `1d92c268196d346aad957b528a261964e9bdcb4d` → `2b76321cc2d354c04d097ec4502777d8fa4838df` → `cfd553e1c0dbce72a91232e00a4080da8d492e0f`
- UTF-8-surrogate RED/fix: `80745c3ca25e4194062dadf13d86f6783067643c` → `95facece4505db2992e6c69a173a4edb4dbc31dc`

## References

Bray, T. (2017). *The JavaScript Object Notation (JSON) Data Interchange Format* (RFC 8259; STD 90). Internet Engineering Task Force. https://doi.org/10.17487/RFC8259

Python Software Foundation. (2026). *json — JSON encoder and decoder (Python 3.14.7 documentation)*. https://docs.python.org/3.14/library/json.html
