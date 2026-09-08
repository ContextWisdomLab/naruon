# Structural topic-model boundary

**Architecture decision:** [`ADR-0001`](../adr/0001-topic-measurement-authority.md) defines Naruon's local policy for truthful topic-measurement consumption. This doctoring record supplies the scientific rationale and evidence; neither record assigns authority to TEPP, records TEPP acceptance, or promotes a future integration to protected-branch implementation.

## Defect record

Naruon previously exposed `email_categorizer` and
`meeting_agenda_generator`, whose outputs came from small hard-coded
Korean/English term lists rather than a fitted topic model. The traceable record
is deliberately narrow: commit
`c070c8d19f01ccfe46a5ee7e8a577b08e587bb14` described basic length/keyword
parsing and a 100%-coverage goal; commit
`699d7ef9d1285c8c2c5a1a38c6732117d0ff703e` made the tables deterministic;
commit `11a329fa3950a529d3df607e33ae09f55117a09d` established the later bound; and
the first merge to `develop` was
`eae74e215d99af49764a765b74e9679037b8fbbe` (PR #1075). These facts describe
the observable history, not unrecorded author intent.

The two pseudo-model tools are now removed on PR #1297. `keyword_extractor`
remains because it honestly exposes deterministic term-frequency extraction. Its
output is lexical metadata, not topic-posterior evidence. Until PR #1297 merges,
this removal remains active-PR behavior rather than a protected-`develop` claim.

## Measurement boundary

Structural topic modeling estimates a mixed-membership vector
\(\theta_d\) for each document: multiple latent topics can contribute to one
document, and metadata may affect topic prevalence or content. A fixed-label
classifier instead selects or scores predefined business labels. Even when a
classifier uses keywords, embeddings, or an LLM, its label or score is not an
STM posterior and must not be presented as one.

New-document STM inference also depends on a fitted corpus-level model and its
frozen vocabulary and preprocessing. Naruon must not fit a topic model inside a
single API request, substitute a larger dictionary, or degrade to embeddings or
LLM labels while calling the result STM.

## Potential future Naruon consumption

Naruon has no independently published TEPP production topic-measurement
artifact/API/contract or TEPP acceptance evidence to consume. The present change
therefore fails closed: when a fitted model is unavailable, no default `General`
label, agenda template, or synthetic posterior is returned.

A future Naruon adapter remains blocked until TEPP independently publishes a
versioned production fitted-model artifact/API/contract and its own acceptance
evidence. If Naruon later evaluates such a published contract, its local
acceptance criteria include:

- immutable document and model-artifact identifiers, model version, and content
  and vocabulary digests;
- document, event, assertion, availability, and knowledge-cutoff times;
- frozen preprocessing, retained-token rules, frozen vocabulary, explicit OOV
  handling, and language identification/support status;
- prevalence/content design specifications and relevant multilevel or
  cross-classified multiple-membership covariates;
- mixed-membership topic proportions summing to one, inference method,
  posterior uncertainty, diagnostics, and explicit abstention criteria/status;
- evidence-backed human-readable labels kept separate from numeric topic
  identity; and
- explicit model-unavailable, incompatible-language, insufficient-retained-
  token, and out-of-vocabulary errors.

The integration is an optional typed service/model-artifact boundary. Naruon must
not read TEPP's private database, infer model compatibility from a display label,
or persist a generated human-readable topic label as the numeric topic identity.

Agenda generation, if reintroduced, belongs behind a separate decision and
generation boundary that consumes source evidence and the versioned posterior.
No copyrighted paper is attached here; redistribution permission has not been
established.

## References

Roberts, M. E., Stewart, B. M., & Tingley, D. (2019). stm: An R package for
structural topic models. *Journal of Statistical Software, 91*(2), 1–40.
https://doi.org/10.18637/jss.v091.i02

This paper specifies the fitted STM workflow, prevalence/content covariates,
posterior quantities, and diagnostics implemented by the `stm` package. It
supports the boundary because a term lookup lacks those fitted-model and
uncertainty semantics.

Roberts, M. E., Stewart, B. M., Tingley, D., Lucas, C., Leder-Luis, J.,
Gadarian, S. K., Albertson, B., & Rand, D. G. (2014). Structural topic models
for open-ended survey responses. *American Journal of Political Science,
58*(4), 1064–1082. https://doi.org/10.1111/ajps.12103

This paper introduces STM for open-ended responses and demonstrates how
document metadata enters topic prevalence/content while documents remain mixed
memberships. It supports separating corpus-level measurement from fixed-label
classification. Redistribution permission for either article has not been
established, so this PR cites, links, and summarizes them without committing
copies.
