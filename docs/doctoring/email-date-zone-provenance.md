# Email Date zone provenance

## Problem

Email import provenance distinguishes a parsed source `Date` from collection-time fallback values because only complete source evidence may participate in strong metadata fingerprinting. Python's `email.utils.parsedate_to_datetime()` returns a naive `datetime` for both RFC 5322 `-0000` and non-conforming Date values that omit a zone entirely. Treating every naive result as UTC therefore promoted a zone-less Date to `date_evidence=parsed` and allowed it to become strong dedupe evidence.

## Constraint

RFC 5322 §3.3 defines `time = time-of-day zone`; a zone is part of the Date-time grammar. `+0000` identifies UTC. `-0000` also denotes the same UTC instant while stating that the sender's local-zone information is unavailable. RFC 5322 §4.3 additionally treats unknown obsolete zones as equivalent to `-0000` for comparison purposes.

Naruon's parser therefore separates two cases that the Python parser exposes with the same naive `datetime` representation:

- a syntactically present `-0000` or obsolete alphabetic zone remains valid source evidence and is bound to UTC for storage/comparison;
- a Date value with no trailing zone is marked `invalid`, receives a collection-time UTC fallback for storage, and cannot participate in a strong metadata fingerprint.

The fallback instant is not presented as source metadata evidence.

## Evidence lineage

- Source-order RED `05e35827ca91a15c21c2f6e3be2498e5a3091fcc` adds route-independent parser/fingerprint regressions. The zone-less example must produce `date_evidence=invalid` and no strong fingerprint, while `-0000` must remain parsed and UTC-comparable.
- Causal production fix `8ed225a941defc985aa54bbe91e359abc1d5654f` distinguishes a trailing RFC 5322/obsolete zone token before assigning UTC to a naive parsed value. No filename-date promotion, Message-ID policy, persistence schema, or unrelated parser behavior is changed.

Hosted evidence must be tied to the post-retarget exact base/head; predecessor direct-`develop` results and pre-retarget workflow generations are not acceptance evidence for this child.

## Reference

Resnick, P. W. (2008). *Internet Message Format* (RFC 5322). Internet Engineering Task Force. https://doi.org/10.17487/RFC5322
