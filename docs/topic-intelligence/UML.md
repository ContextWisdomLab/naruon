# Topic intelligence UML views

- **Capability maturity:** `BLOCKED-UPSTREAM`
- **Document status:** `PRESENT-CURRENT`
- **Contract revision:** `2026-08-09.1`

These diagrams describe a planned integration boundary. They do not represent
deployed classes, routes, tables, or an accepted TEPP production API. TEPP is
only the expected upstream producer if it independently publishes a compatible
production contract, fitted artifact, and acceptance evidence.

## Contract structure

The Naruon-owned envelope controls authorization, revisioning, validation, and
safe projection. The nested scientific payload carries fitted-model evidence
and estimates; presentation labels stay outside that payload.

```mermaid
classDiagram
    class TopicInferenceEnvelope {
        +ContractIdentity contract
        +RequestIdentity request
        +ResultStatus status
        +datetime completed_at
        +CanonicalDigest tepp_payload_digest
    }
    class TEPPScientificPayload {
        +ScientificProvenance provenance
        +InferenceResult inference
        +DiagnosticBundle diagnostics
    }
    class InferenceResult {
        +number credible_level
        +string interval_method
        +string uncertainty_scope
        +integer topic_count
    }
    class PosteriorComponent {
        +integer topic_id
        +integer rank
        +number proportion
        +CredibleInterval credible_interval
    }
    class PresentationLabel {
        +integer topic_id
        +string label_id
        +string label_version
        +string language
        +string label
        +OpaqueEvidenceRef[] evidence_refs
    }

    TopicInferenceEnvelope *-- TEPPScientificPayload
    TEPPScientificPayload *-- InferenceResult
    InferenceResult *-- PosteriorComponent
    TopicInferenceEnvelope o-- PresentationLabel
```

`PresentationLabel.topic_id` may reference a posterior component but cannot
change its identifier, rank, proportion, interval, or diagnostic outcome.
The public projection preserves opaque model ID/version, analysis unit,
estimand, coarse covariate level, and causal/non-causal designation while
redacting canonical digests, scope bindings, raw covariates, and group values.

## Provenance and diagnostics

```mermaid
classDiagram
    class ScientificProvenance {
        +string model_id
        +string model_version
        +integer fitted_topic_count
        +string temporal_policy_version
        +string estimator_id
        +string analysis_unit
        +string estimand_id
        +string causal_design
    }
    class CanonicalDigest {
        +string algorithm
        +string canonicalization
        +string domain
        +string value
    }
    class DesignContract {
        +string covariate_schema_version
        +string covariate_level
        +string covariate_missingness_policy
        +string prevalence_formula
        +string content_formula
        +string contrast_specification
        +string membership_structure
        +string membership_weight_normalization
        +string unseen_level_policy
    }
    class DiagnosticBundle {
        +string diagnostic_status
        +InputDiagnostics input
        +PosteriorDiagnostics posterior
        +PolicyDiagnostics policy
    }
    class PosteriorDiagnostics {
        +string diagnostic_code_registry_version
        +boolean converged
        +string convergence_code
        +string numerical_status
        +string[] quality_codes
    }
    class PolicyDiagnostics {
        +string policy_version
        +string reason_code_registry_version
        +boolean accepted
        +string[] reason_codes
    }

    ScientificProvenance *-- CanonicalDigest
    ScientificProvenance *-- DesignContract
    DiagnosticBundle *-- PosteriorDiagnostics
    DiagnosticBundle *-- PolicyDiagnostics
```

The single `CanonicalDigest` association represents the required schema,
snapshot, scientific payload, artifact descriptor, artifact manifest, vocabulary,
preprocessing, design, lineage, model-card, validation-report, evidence-time,
covariate-snapshot, and design-row digests. Each use has its own fixed domain
separator.

## Planned request sequence

```mermaid
sequenceDiagram
    participant U as Naruon client
    participant R as Naruon route
    participant A as Topic adapter
    participant T as Expected upstream boundary

    U->>R: document_ref, evidence_ref, revision
    R->>R: Authenticate and reauthorize
    alt Authentication or scope denied
        R-->>U: 401 or 403 Problem + error_code
    else Rate policy exceeded
        R-->>U: 429 Problem + error_code
    else Authorized
        R->>A: Immutable canonical snapshot request
        A->>A: Preflight and pin deployment
        alt Preflight ineligible
            A-->>R: 422 Problem + error_code
        else No active model or artifact
            A-->>R: 503 Problem + error_code
        else Revision or idempotency conflict
            A-->>R: 409 Problem + error_code
        else Compatible
            A->>T: Versioned scientific request
            alt Upstream deadline expires
                A-->>R: 504 Problem + bounded cancellation
            else Scientific payload returned
                T-->>A: Expected scientific payload
                A->>A: Verify schema, digests, codes, cross-fields
                alt Payload validation fails
                    A-->>R: 502 Protocol Problem + error_code
                else Accepted posterior
                    A-->>R: 200 inferred envelope
                else Posterior or policy rejected
                    A-->>R: 200 abstained envelope
                end
            end
        end
        R-->>U: Redacted safe projection or Problem
    end
```

An expired, wrong-audience, wrong-snapshot, or wrong-tenant evidence reference
is rejected before the adapter call. The route must resolve the reference
server-side; it must never dereference an arbitrary client URL or path.

## Result state model

```mermaid
stateDiagram-v2
    [*] --> Received
    Received --> Rejected422: Ineligible preflight
    Received --> RejectedAuth: Authentication or scope denial
    Received --> RateLimited429: Quota or rate denial
    Received --> Conflict409: Trusted request conflict
    Received --> Unavailable503: No active deployment
    Received --> Eligible: Compatible input and model
    Eligible --> Inferring
    Inferring --> ProtocolFault502: Unusable upstream response
    Inferring --> Deadline504: Upstream deadline
    Inferring --> Cancelled: Client cancellation
    Inferring --> Validating: Scientific payload returned
    Validating --> ProtocolFault502: Schema, digest, code, or invariant fails
    Validating --> Inferred: Posterior accepted
    Validating --> Abstained: Posterior or policy rejected
    Rejected422 --> [*]
    RejectedAuth --> [*]
    RateLimited429 --> [*]
    Conflict409 --> [*]
    Unavailable503 --> [*]
    ProtocolFault502 --> [*]
    Deadline504 --> [*]
    Cancelled --> [*]
    Inferred --> [*]
    Abstained --> [*]
```

The state model intentionally has no fallback transition from an error or
abstention to a default topic, lexical classifier, embedding cluster, LLM label,
or agenda template.

## Deployment compatibility state

```mermaid
stateDiagram-v2
    [*] --> Discovered
    Discovered --> Quarantined: Missing upstream evidence
    Discovered --> Verifying: Published contract found
    Verifying --> Quarantined: Digest or validation failure
    Verifying --> Inactive: Compatible evidence verified
    Inactive --> Active: Operator activation
    Active --> Revoked: Artifact or policy revoked
    Active --> Inactive: Controlled rollback
    Revoked --> Verifying: New immutable revision
```

Only `Active` can serve inference. A display name, mutable tag, or previously
seen model ID is not sufficient deployment evidence.

## Cross-field validation obligations

The schema validates local types, bounds, and status-dependent shape. The
adapter must additionally validate:

- non-negative integer topic IDs, rank uniqueness, and, for `inferred`, equality
  of fitted, declared, observed, and actual component counts;
- component sum within the pinned tolerance;
- estimate containment within each credible interval;
- equality between recomputed and reported diagnostic counts/sums;
- status, diagnostic acceptance, and reason-code consistency;
- request/evidence snapshot equality, scope-binding equality, expiry, and current
  tenant/workspace/purpose/consent/region reauthorization;
- RFC 3339 format assertion, availability-at-knowledge-cutoff ordering, and the
  pinned temporal missingness rule;
- exact diagnostic/reason-code registry versions and known-code membership, with
  unknown versions or codes mapped to `502`;
- deployment identity and every pinned provenance digest;
- design formula/contrast, estimator, analysis-unit, estimand, covariate schema,
  level/missingness, membership structure/normalization coupling, unseen-level,
  temporal, and validation-profile compatibility; and
- reauthorization of each opaque evidence reference at the time of use.

See [API contract](API_CONTRACT.md) for HTTP semantics and
[conceptual data model](DATA_MODEL.md) for ownership relationships.
