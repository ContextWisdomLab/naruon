# Operating the auditable data-hygiene tools

The tools are private, signed-session-protected entries in `/api/tools`.

1. Call `GET /api/tools` with the normal Naruon session.
2. Execute `url_evidence_extractor` with `{"parameters":{"text":"..."}}`
   when links need review. Treat `validation_status` and `warning_codes` as
   required review evidence; extraction never implies the link is safe.
3. Execute `contact_data_redactor` with the same parameter shape when a working
   copy needs supported email/phone placeholders. Preserve the returned match
   spans with the redacted text for auditability.
4. Stop and present the stable `error_code` when an input bound is exceeded.

Do not submit real customer mail to public CI or fixtures. These tools do not
replace access control, retention, deletion, encryption, authenticated message
integrity, or a complete privacy/anonymization assessment.
