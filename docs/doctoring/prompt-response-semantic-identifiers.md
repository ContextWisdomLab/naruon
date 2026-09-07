# Prompt response semantic identifiers

## Decision

Naruon's Prompt Catalog bounded context already has an opaque public identifier, `prompt_uid`, and a separate sequential database row identity, `PromptTemplate.id`. The public `/api/prompts` list and create responses expose only `prompt_uid`; the sequential row identity is not part of `PromptResponse`.

A naming-only approach that aliases the sequential database identity under a more descriptive internal name is insufficient because it still exports an unnecessary enumerable identifier. The canonical public contract therefore removes both bare `id` and any renamed row-id alias instead of merely recasing or relabeling them.

| Previous public field | Current public field | Meaning |
| --- | --- | --- |
| `id` (sequential database row id) | removed | private persistence identity |
| `prompt_uid` | `prompt_uid` | opaque public prompt identity |

## DDD, security, and compatibility boundary

- **Bounded context:** Prompt Catalog.
- **Entity:** persisted prompt-template record.
- **Public identity:** `prompt_uid` is the sole prompt identifier in list/create response contracts.
- **Persistence identity:** `PromptTemplate.id` remains private to persistence and may still exist on ORM records; Pydantic `from_attributes=True` ignores it because it is not a response field.
- **Authorization invariant:** organization/workspace ownership filters on `list_prompts` and creation ownership assignments remain unchanged. Opaque identifiers are defense-in-depth and do not replace object-level authorization.
- **Public contract:** the redundant sequential `id` response property is intentionally absent. Consumers use the already-present `prompt_uid` for prompt identity.
- **Persistence:** unchanged. No database migration, backfill, index change, new lock, UPSERT change, partition change, or read/write split is introduced.

OWASP API Security Top 10 API1:2023 notes that object identifiers, including sequential integers, are common BOLA attack inputs and recommends random, unpredictable record identifiers together with proper object-level authorization. Naruon already has the unpredictable `prompt_uid`, so retaining a second sequential public identifier has no buyer-visible product benefit and widens the identifier surface unnecessarily.

## Verification contract

`backend/tests/test_prompts_api.py` verifies that create/list responses omit `id` while returning opaque `prompt_uid`. `backend/tests/test_prompt_response_naming_contract.py` additionally validates an ORM-shaped record that still contains private `id=17` and requires both runtime serialization and generated JSON schema to omit `id` and `prompt_record_id` while retaining `prompt_uid`. Exact-head repository CI, security workflows, review threads, and branch protection remain authoritative merge evidence.

## Research traceability

Empirical software-engineering research supports treating identifier names as program-comprehension artifacts rather than cosmetic style. Feitelson et al. found that explicitly choosing the concepts represented in a name improved judged name quality and tended to produce names containing more concepts; later replication work corroborated that model and found that merely making names longer was not equivalent to selecting meaningful concepts. Here the stronger domain conclusion is that the public concept is already fully represented by `prompt_uid`; a second database-row identifier should not be renamed and exported when it is not part of the public domain language.

### References

Alpern, R., Lazer, I., Tzachor, I., Hakim, H., Weissbuch, S., & Feitelson, D. G. (2024). *Reproducing, extending, and analyzing naming experiments*. arXiv. https://doi.org/10.48550/arXiv.2402.10022

Feitelson, D. G., Mizrahi, A., Noy, N., Ben Shabat, A., Eliyahu, O., & Sheffer, R. (2022). How developers choose names. *IEEE Transactions on Software Engineering, 48*(1), 37–52. https://doi.org/10.1109/TSE.2020.2976920

OWASP Foundation. (2023). *API1:2023 Broken Object Level Authorization*. OWASP API Security Top 10. https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
