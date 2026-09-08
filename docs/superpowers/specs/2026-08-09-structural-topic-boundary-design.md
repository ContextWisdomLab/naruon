# Structural Topic Boundary Design

**Status:** Active PR deletion design for PR #1297; removal is not
protected-`develop` behavior until merge. This file's former future-integration
summary is `SUPERSEDED` by the canonical package below. The Naruon-local policy
is accepted, the target decisions remain proposed, and runtime topic inference
is `BLOCKED-UPSTREAM` and unimplemented.

**Canonical documentation graph:**
[`docs/topic-intelligence/README.md`](../../topic-intelligence/README.md)

That package and its linked ADR index govern maturity, authority, requirements,
the 14-field digest inventory, and error-versus-abstention semantics. This legacy
design remains useful for the deletion history only. It does not assign product
or scientific authority to TEPP or another producer, impose an external
obligation, record upstream acceptance, or establish a production contract.

## Context

Protected `develop` exposes `email_categorizer` and
`meeting_agenda_generator` as analysis tools, but both derive their outputs from
small hard-coded Korean/English term lists. The behavior entered in commit
`c070c8d19f01ccfe46a5ee7e8a577b08e587bb14` as demonstration logic and was
later made deterministic and better tested without correcting the underlying
measurement error. The tests consequently canonized lexical hits as topic
evidence.

Structural topic modeling (STM) is not fixed-label keyword classification. It
estimates mixed-membership topic proportions over a corpus and can model how
document metadata affects topic prevalence or content. Inference for a new
document requires a previously fitted model and its frozen vocabulary; the
result is a topic mixture with uncertainty, not a calibrated probability for a
business label.

## Decision

1. Remove `email_categorizer` and `meeting_agenda_generator` from Naruon's tool
   registry. They have no callers outside their own tests, so removal eliminates
   misleading product behavior without breaking an integrated workflow.
2. Remove `_CATEGORY_TERMS`, `_AGENDA_TOPICS`, and the substring matcher that
   exists only to support those pseudo-models.
3. Retain `keyword_extractor` as an explicitly lexical utility, but describe it
   honestly as deterministic term-frequency extraction. Its output must never
   be treated as topic posterior evidence.
4. Do not add an embedding, LLM, or larger dictionary fallback and do not call
   any such fallback STM.
5. Keep corpus-level topic estimation outside this Naruon deletion change.
   TEPP's Rust-first `topic_measurement` architecture is directional evidence,
   not an assignment of authority. Naruon may evaluate any independently
   published, compatible fitted-model boundary only after its publisher releases
   a versioned, source-backed artifact/inference contract and acceptance evidence,
   and Naruon separately accepts the integration. Until then, absence of a fitted
   model fails closed rather than returning `General` or a template agenda.

## Conditional future Naruon acceptance profile

The accepted local policy is [ADR-0001](../../adr/0001-topic-measurement-authority.md).
The fitted-artifact and agenda target decisions remain proposed in
[ADR-0002](../../adr/0002-fitted-topic-artifact-consumption.md) and
[ADR-0003](../../adr/0003-separate-topic-measurement-from-agenda-generation.md).
The following are conditions Naruon would apply to its own consumption decision;
they do not govern an upstream publisher.

Any later Naruon integration must bind all 14 exact fields in the canonical
[digest inventory](../../topic-intelligence/README.md#canonical-digest-inventory),
including the schema, source snapshot, complete scientific payload, artifact,
manifest, vocabulary, preprocessing, design, lineage, model card, validation
report, evidence-time manifest, covariate snapshot, and design row. It must also
carry, at minimum:

- immutable document, snapshot, model, artifact, and contract identities;
- document, event, assertion, availability, and knowledge-cutoff times;
- language and multilevel/cross-classified membership covariates;
- the frozen preprocessing and prevalence/content design specifications;
- topic proportions that sum to one, posterior uncertainty, inference method,
  model version, and diagnostic status;
- evidence-backed topic labels kept separate from the numeric topic identity;
- explicit input, incompatibility, integrity, availability, and protocol errors;
  and
- `abstained` only for a compatible active model's declared posterior or
  diagnostic-policy rejection, never for an error or fallback.

If Naruon later accepts and implements agenda generation, that capability must
consume authorized source evidence and, optionally, a versioned posterior through
a separate decision/generation boundary. It must not map raw words directly to
agenda templates. Proposed ADR-0003 is not implementation authorization.

## Alternatives rejected

- **Expand the dictionaries:** deterministic but still lexical, brittle across
  language and domain, and unable to represent mixed membership or uncertainty.
- **Use embeddings or an LLM as a drop-in replacement:** potentially useful for
  semantic labeling, but neither is STM and neither supplies the required
  corpus-level estimand or covariate effects.
- **Fit a model inside each API request:** statistically invalid for a single
  document, operationally expensive, and incompatible with reproducible model
  artifacts.

## Verification

- The pre-change regression test failed because the two misleading tool codes
  were registered.
- On PR #1297, the registry omits both codes while retaining the
  explicitly lexical term-frequency utility.
- Focused tools tests, the complete backend test suite with warnings promoted to
  errors, and Ruff must pass.

## References

Roberts, M. E., Stewart, B. M., & Tingley, D. (2019). stm: An R package for
structural topic models. *Journal of Statistical Software, 91*(2), 1–40.
https://doi.org/10.18637/jss.v091.i02

The package paper defines a fitted STM workflow with covariate-aware prevalence
and content, posterior quantities, and diagnostics. Those requirements are why
a deterministic term table cannot satisfy the measurement contract.

Roberts, M. E., Stewart, B. M., Tingley, D., Lucas, C., Leder-Luis, J.,
Gadarian, S. K., Albertson, B., & Rand, D. G. (2014). Structural topic models
for open-ended survey responses. *American Journal of Political Science,
58*(4), 1064–1082. https://doi.org/10.1111/ajps.12103

The application paper establishes mixed-membership topics whose prevalence or
content can vary with document metadata. It grounds the design's separation of
corpus-level inference from fixed business labels. Redistribution permission
for either article has not been established; citations, links, and summaries
are supplied instead of paper copies.
