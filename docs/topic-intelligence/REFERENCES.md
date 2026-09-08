# Topic intelligence references

**Snapshot date:** 2026-08-09 (Asia/Seoul)

**Maturity:** reference design `PLANNED`; runtime integration
`BLOCKED-UPSTREAM`

These sources ground the scientific, provenance, risk, security-development,
and wire-contract boundaries. A citation does not establish Naruon or TEPP
conformity, certification, production readiness, or implementation.

## Structural topic modeling

Roberts, M. E., Stewart, B. M., Tingley, D., Lucas, C., Leder-Luis, J.,
Gadarian, S. K., Albertson, B., & Rand, D. G. (2014). Structural topic models
for open-ended survey responses. *American Journal of Political Science, 58*(4),
1064–1082. https://doi.org/10.1111/ajps.12103

Roberts, M. E., Stewart, B. M., & Tingley, D. (2019). stm: An R package for
structural topic models. *Journal of Statistical Software, 91*(2), 1–40.
https://doi.org/10.18637/jss.v091.i02

These works support mixed-membership topic estimation, document-level metadata,
and uncertainty-aware analysis. They do not by themselves establish a
multilevel, multiple-membership, cross-classified, longitudinal, multilingual,
or production-serving estimator. Naruon remains blocked from accepting any such
upstream extended-STM design unless independently published evidence names the
method and estimand, freezes formulas/contrasts, and supplies separate known-truth
validation. This acceptance condition assigns no obligation to TEPP.

## Risk, security, and provenance standards

National Institute of Standards and Technology. (2023). *Artificial
Intelligence Risk Management Framework (AI RMF 1.0)* (NIST AI 100-1).
https://doi.org/10.6028/NIST.AI.100-1

National Institute of Standards and Technology. (2022). *Secure Software
Development Framework (SSDF) version 1.1: Recommendations for mitigating the
risk of software vulnerabilities* (NIST SP 800-218).
https://doi.org/10.6028/NIST.SP.800-218

National Institute of Standards and Technology. (2024). *Secure software
development practices for generative AI and dual-use foundation models: An SSDF
community profile* (NIST SP 800-218A).
https://doi.org/10.6028/NIST.SP.800-218A

International Organization for Standardization. (2023). *ISO/IEC 42001:2023—
Information technology—Artificial intelligence—Management system*.
https://www.iso.org/standard/42001.html

International Organization for Standardization. (2023). *ISO/IEC 23894:2023—
Information technology—Artificial intelligence—Guidance on risk management*.
https://www.iso.org/standard/77304.html

World Wide Web Consortium. (2013). *PROV-O: The PROV ontology* (W3C
Recommendation). https://www.w3.org/TR/prov-o/

These sources inform risk ownership, lifecycle evidence, secure development,
and provenance. The documents in this package use them as design guidance and
make no audit or certification claim.

## Wire-contract standards

Nottingham, M., Wilde, E., & Dalal, S. (2023). *Problem details for HTTP APIs*
(RFC 9457). RFC Editor. https://www.rfc-editor.org/rfc/rfc9457.html

Rundgren, A., Jordan, B., & Erdtman, S. (2020). *JSON Canonicalization Scheme
(JCS)* (RFC 8785). RFC Editor. https://www.rfc-editor.org/rfc/rfc8785.html

JSON Schema. (2020). *JSON Schema specification: Draft 2020-12*.
https://json-schema.org/draft/2020-12

JSON Schema. (2020). *JSON Schema validation: A vocabulary for structural
validation of JSON* (Draft 2020-12).
https://json-schema.org/draft/2020-12/json-schema-validation

RFC 9457 grounds the planned HTTP problem-details shape only after a transport
ADR selects HTTP. RFC 8785 grounds deterministic canonical JSON bytes for the
planned domain-separated digest contract; it does not normalize Unicode. Draft
2020-12 grounds the planned Naruon adapter schema. Its `format` keyword does not
by itself prove that a chosen validator asserts date-time validity; Naruon's
future validator and fixtures must exercise the required format behavior. Exact
schema identity, revision, and digest must be immutable and pinned; the checked
schema is not a deployed OpenAPI component or TEPP's canonical payload.

## Inspected TEPP repository evidence

- Repository: [ContextualWisdomLab/tepp](https://github.com/ContextualWisdomLab/tepp)
- Exact inspected protected-`main` revision:
  [`b8e26aae334397daa1974d4a24c9015cfd682600`](https://github.com/ContextualWisdomLab/tepp/commit/b8e26aae334397daa1974d4a24c9015cfd682600)
- Commit timestamp: `2026-08-06T11:33:18+09:00`
- Inspection date: `2026-08-09` (Asia/Seoul)

At that exact revision, `crates/evidence_core/` contains immutable evidence
domain primitives and the JSON wire boundary. `ARCHITECTURE.md` names
`topic_measurement` only in the target architecture. There is no corresponding
production topic-measurement crate or endpoint, and
`crates/tepp_api/src/lib.rs` explicitly states that the foundation slice exposes
no production behavior. The observation is revision-bound and must be refreshed
before any implementation or maturity claim.
