# Reply subject prefix compatibility

Observed: 2026-09-11

## Problem

`buildReplyPayload()` recognized only the exact prefix `Re:`. Messages whose existing reply marker used another ASCII case, such as `RE:`, `re:`, or `rE:`, therefore received an additional generated prefix and became `Re: RE: ...` or equivalent. That creates avoidable subject drift and can fragment conversations in clients that use subject text as a secondary threading signal.

## Constraint

RFC 5322 section 3.6.5 permits a reply Subject field body to begin with `Re: ` followed by the original subject and says that only one instance ought to be used because multiple instances can have undesirable consequences. Naruon continues to generate the canonical `Re: ` spelling for a subject that has no reply marker.

RFC 5322 does not require Naruon to rewrite the case of an already-present human-readable Subject prefix. For interoperability, this boundary treats the ASCII case variants `Re:`, `RE:`, `re:`, and mixed-case equivalents as the same reply marker and preserves the sender-visible original spelling. The match remains anchored at the start of the subject and requires the colon, so ordinary words beginning with `re` such as `Release notes` are not classified as reply markers.

## Decision

Use a start-anchored ASCII case-insensitive `^re:` check. Do not normalize the existing subject text after the marker has been recognized. For an unprefixed or empty subject, keep the existing generated form `Re: ${subject}`.

Rejected alternatives:

- exact-case `startsWith("Re:")`: preserves duplicate-prefix behavior for common case variants;
- lowercasing the full subject before comparison or output: changes user-visible content beyond the interoperability requirement;
- broad `^re` matching: misclassifies ordinary subjects such as `Release notes`.

## Evidence

The original candidate added uppercase and lowercase regression cases. After adopting the canonical frontend dependency-security parent `#1623@17a7618eda2b212b691f08fa936e042b34258fc9`, the current regression set also covers mixed-case `rE:` and a non-prefix `Release notes` control. The product change remains limited to `frontend/src/lib/email-threading.ts`; the focused contract lives in `frontend/src/lib/email-threading.test.ts`.

Direct-`develop` workflow receipts from the predecessor are historical after the parent topology changes. Exact current-base/head execution and independent post-last-push review are required before merge.

## Reference

Resnick, P. W. (2008). *Internet Message Format* (RFC 5322). Internet Engineering Task Force. https://doi.org/10.17487/RFC5322
