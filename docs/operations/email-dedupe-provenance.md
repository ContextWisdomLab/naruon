# Email Dedupe Provenance

## Purpose

Email import keeps the source date separate from the time used to store a
message when the RFC 5322 `Date` header is missing or invalid. This prevents a
collection-time fallback from becoming duplicate evidence.

The persisted `email_records` fields are:

- `date_evidence`: `parsed`, `missing`, or `invalid`.
- `message_id_evidence`: `embedded` or `missing`.

Existing rows may have `NULL` values until they are re-imported or backfilled
by a separately reviewed migration. `NULL` means unknown, not valid source
evidence.

## Import Decisions

The import response contains one item per source file. `reason_code` describes
the import disposition:

- `duplicate_email`: an existing scoped message matched.
- `dedupe_review_required`: the message was stored, but missing or invalid
  date metadata prevented a metadata fingerprint from being used.
- `NULL`: the item was imported with complete parsed metadata, or no special
  disposition applies.

The importer internally distinguishes the strongest observed duplicate basis:

- `embedded_message_id`: the normalized embedded `Message-ID` matched.
- `raw_content_fallback_message_id`: the deterministic SHA-256 identity for a
  message without an embedded `Message-ID` matched.
- `metadata_fingerprint`: complete sender, subject, recipients, body, and
  parsed source date matched the scoped fingerprint. API serialization of this
  field remains owned by the active email API security lane and is not claimed
  as shipped by this slice.

The response exposes no message body, credentials, or raw secret-derived
values. Provider writes are not performed by this import surface:
`provider_write_executed` remains `false`.

## Migration

Apply Alembic revision `email_metadata_provenance_1086` before relying on the
persisted fields in a deployed database:

```sh
cd backend
uv run alembic upgrade head
```

Run this only against an explicitly selected isolated or deployment database
with its normal runtime settings. Do not infer migration success from unit
tests or offline rendering alone.

## Limitations

This contract is provenance-aware deduplication, not anonymization or a claim
that every related message can be automatically resolved. Missing or invalid
source metadata remains reviewable. File-name dates are never promoted to
source-date evidence.
