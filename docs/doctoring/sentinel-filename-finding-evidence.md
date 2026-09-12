# Sentinel filename-finding evidence doctoring

## Scope

This note defines the evidence boundary for Sentinel findings that infer executable-upload risk from an uploaded filename. It records why Naruon issue #1666 and PR #1667 correct the 2024-06-25 `.jules/sentinel.md` lesson without weakening the product's existing email-import path, terminal-suffix, control-character, bounded-decoding, and parser-only controls.

The rule is deliberately narrower than “double extensions are safe.” A double or embedded extension can be exploitable when a downstream server, interpreter, handler, storage layer, MIME decision, suffix-stripping step, shell, or process boundary gives the inner extension execution or reinterpretation semantics. Sentinel must reproduce that consumer/sink relationship before classifying the filename pattern itself as a HIGH/CRITICAL exploit.

## Finding and falsification

Generated PR #1661 treated a name such as `malicious.exe.eml` as a demonstrated executable-upload bypass and proposed a filename-segment denylist. Fresh verification against protected `develop@042b0c70531b229af3acbd0421a2f23098d848b3` did not reproduce a consumer that strips the terminal `.eml`, executes the intermediate segment, changes MIME handling because of it, or hands the filename to an unsafe shell/process boundary. The generated denylist also selected some embedded extensions while leaving other executable-looking segments untouched, so the patch did not express a coherent product invariant. #1661 was restored to zero effective delta and closed unmerged; #1666 owns the Sentinel-authority root cause.

This falsification does not contradict established upload-security guidance. OWASP documents double extensions as a bypass class when extension parsing or downstream handling makes an inner extension meaningful, and recommends defense in depth rather than relying on extension blocking alone. CWE-434 likewise describes environments in which an inner extension can remain active, while warning against exclusive reliance on malformed-input denylists. Those authorities support validating the actual interpretation and execution boundary; they do not establish that every filename containing an executable-looking intermediate segment is itself an exploit.

## RED → repair

Source-order RED `f2124eb7e688bda40b448d627fd3e8f9a99e92cf` adds `backend/tests/test_sentinel_security_guidance.py`. The regression requires the 2024-06-25 lesson to:

- state that an embedded extension alone is insufficient evidence;
- require a reproduced consumer or sink before HIGH/CRITICAL classification;
- preserve execution/interpreter, MIME/content-type, suffix-stripping/reinterpretation, and shell/process evidence categories;
- stop prescribing an arbitrary `split(".")` embedded-extension denylist; and
- retain explicit SMTP CRLF rejection plus canonical path, control-character, terminal-suffix, and parser-only upload boundaries.

Minimal repair `4192b4ee29b219deb646d553d10e3eb766fb64de` changes only the stale Sentinel lesson. Exact `4192b4ee...` completed the repository backend Python 3.14 Application CI job successfully. Its direct-develop Security Scan failure was unrelated to the Sentinel delta: Trivy reported the already-owned frontend lockfile findings later adopted from canonical dependency/security owner #1623.

Ordinary ancestry PR #1668 then merged exact #1623 `17a7618eda2b212b691f08fa936e042b34258fc9` into the branch. PR #1667 is stacked on that owner; dependency source is not copied into this lane.

The first exact-range review after retarget found that the filename-evidence test used disconnected keywords and could pass despite contradictory guidance. `7d0bdf0a04ac5d889f0c396799fed3faa04b4e8b` repaired that by asserting the complete causal consumer/sink rule and its preserved upload boundaries.

A second exact-range review found the remaining SMTP regression was still vacuous: it separately searched for `chr(10)`, `chr(13)`, and `mode="before"`, so the lesson could drop `@field_validator`, omit one of the required fields, or negate rejection while retaining those tokens. RED `11e5bdc0dcecd0bd56b8247a93bae913ef1ba8a3` requires one complete normalized policy clause. Causal guidance repair `ca9ef9a624af344e9bb19654b8f68a4315246f15` explicitly requires `@field_validator`, `mode="before"`, rejection of both CR/LF code points, and all four user-controlled fields (`to`, `subject`, `in_reply_to`, `references`). Test-harness child `934caabb1dc3399935479660716359d41c7c7380` strips Markdown code-span backticks during normalization so the regression tests policy semantics rather than Markdown punctuation.

## Decision

Sentinel may record filename patterns as observations, but severity and remediation must follow a reproduced causal path. For an embedded extension, acceptable exploit evidence includes at least one product-relevant boundary such as:

- a web server, runtime, or interpreter selecting the inner extension;
- a downstream consumer stripping or replacing the terminal extension;
- MIME/content-type confusion that changes processing behavior;
- an unsafe shell or process invocation using the attacker-controlled filename; or
- an equivalent storage/retrieval boundary that turns the filename pattern into executable or active content.

If no such sink is reproduced, Sentinel must not manufacture a HIGH/CRITICAL finding or prescribe an arbitrary embedded-extension denylist. It must preserve the existing allowlisted terminal format and canonicalization controls and continue investigating the actual consumer path.

## Rejected alternatives

- Treating every embedded executable-looking extension as a vulnerability was rejected because severity would be disconnected from the product's actual interpretation path and recreated the #1661 false positive.
- Declaring double extensions harmless was rejected because OWASP and CWE-434 document real environments where downstream extension interpretation makes them exploitable.
- Replacing the terminal-format allowlist with a blocklist was rejected because denylisting selected “dangerous” strings is incomplete and duplicates product policy already expressed by supported email-import formats.
- Removing filename checks entirely was rejected because traversal, control characters, terminal suffix validation, storage naming, MIME/content validation, and consumer semantics remain distinct security boundaries.
- Disabling or reducing Sentinel cadence was rejected because the defect was evidence quality, not the existence of recurring security review.
- Keeping token-by-token SMTP assertions was rejected because disconnected keywords do not prove the required validator, rejection semantics, and protected field set remain one normative contract.

## Acceptance boundary

#1666 is not complete merely because the guidance text changed. Acceptance requires the focused governance regression to be GREEN on the unchanged final head, no valid current-head review finding, qualifying independent review, correct stacking on #1623 while that owner remains unintegrated, and eventual protected integration. Hosted receipts whose displayed base was mutated after workflow admission must not be treated as immutable event-time stacked evidence.

## Traceability

- Root-cause issue: `ContextualWisdomLab/naruon#1666`
- Repair PR: `ContextualWisdomLab/naruon#1667`
- Withdrawn generated finding: `ContextualWisdomLab/naruon#1661`
- Protected authority inspected: `develop@042b0c70531b229af3acbd0421a2f23098d848b3`
- Governance RED: `f2124eb7e688bda40b448d627fd3e8f9a99e92cf`
- Initial Sentinel causal fix: `4192b4ee29b219deb646d553d10e3eb766fb64de`
- First review-regression hardening: `7d0bdf0a04ac5d889f0c396799fed3faa04b4e8b`
- SMTP complete-clause RED: `11e5bdc0dcecd0bd56b8247a93bae913ef1ba8a3`
- SMTP guidance repair: `ca9ef9a624af344e9bb19654b8f68a4315246f15`
- Markdown-normalization harness repair: `934caabb1dc3399935479660716359d41c7c7380`
- Canonical frontend dependency/security owner: `ContextualWisdomLab/naruon#1623@17a7618eda2b212b691f08fa936e042b34258fc9`
- Parent-adoption merge: `61aec6b70cc310cb6d59d763190b68d3795fb7d9`

## References

MITRE. (2026). *CWE-434: Unrestricted upload of file with dangerous type* (CWE Version 4.20). Common Weakness Enumeration. https://cwe.mitre.org/data/definitions/434.html

OWASP Foundation. (n.d.). *File upload cheat sheet*. OWASP Cheat Sheet Series. https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
