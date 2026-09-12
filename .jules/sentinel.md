## 2024-05-24 - Overly Permissive CORS Policy

**Vulnerability:** The CORS configuration in FastAPI allowed wildcards (`*`) for `allow_methods` and `allow_headers`.
**Learning:** This could permit unintended cross-origin interaction, potentially exposing the API to Cross-Site Request Forgery (CSRF) or unintended data exposure, particularly via custom headers or unconventional methods.
**Prevention:** Always restrict `allow_methods` and `allow_headers` in CORS policies to the exact methods and headers required by the application.
## 2026-05-28 - Missing Next.js Security Headers
**Vulnerability:** The Next.js frontend was missing critical HTTP security headers (Content-Security-Policy, X-Content-Type-Options, X-Frame-Options, Strict-Transport-Security).
**Learning:** Security headers should be explicitly configured in Next.js applications via the `headers()` method in `next.config.ts`, as they are not included by default.
**Prevention:** Always enforce a strong CSP and other security headers at the application framework level, even if the application is purely API-driven.

## 2025-02-24 - [DAV Path Traversal Vulnerability]
**Vulnerability:** A path traversal vulnerability existed in the `/dav/{path:path}` endpoint where `_dav_path_owner_user_id` extracted the owner user ID using `path.partition("/")` without validating or normalizing `..` segments.
**Learning:** This allowed an attacker to supply a path like `my_user_id/../other_user_id/projects`, tricking the authorization check `_ensure_dav_owner_scope` into passing because the first segment matched their authenticated `user_id`. The remaining path could then be used downstream to access resources of `other_user_id`. When testing this against FastAPI's TestClient, the TestClient normalizes `../` automatically; `..%2F` must be used to test the router correctly.
**Prevention:** Always validate or normalize dynamic paths used for authorization constraints, explicitly rejecting paths containing traversal segments like `..` before parsing hierarchical data.
## 2026-06-20 - Authorization Bypass in Access Policy Evaluation
**Vulnerability:** System admin and platform admin roles could bypass the organization boundary checks and the resource ownership checks in `evaluate_access()` inside `backend/services/access_policy.py`.
**Learning:** This insecure authorization logic allowed a system administrator intended for global operations to have unconstrained horizontal and vertical privilege escalation over arbitrary resources owned by other organizations and other users.
**Prevention:** Access policy evaluations must unconditionally evaluate constraints like `organization_id` matching and `owner_id` matching, applying authorization boundaries strictly independent of the role unless explicitly designed to supersede those checks for specific resources.
## 2025-02-20 - MD5 to SHA-256 for Security Scanner Compliance
**Vulnerability:** MD5 used for hashing random parameters for DB table unique IDs.
**Learning:** Using MD5, even for non-cryptographic purposes like generating unique IDs from randomness, triggers security scanners. Cryptographically weak functions like MD5 should not be used when stronger ones are available.
**Prevention:** In SQL queries and backend code, prefer using `encode(sha256((...)::bytea), 'hex')` over `md5(...)` to generate deterministic hashes or unique IDs to maintain compliance and security.

## 2026-06-20 - Missing Auth on update_tenant_config (Already Mitigated)
**Vulnerability:** A previous state of the codebase was reported to be missing `Depends(get_auth_context)` on `update_tenant_config`.
**Learning:** `auth_ctx: AuthContext = Depends(get_auth_context)` is already correctly implemented in the endpoint signature.
**Prevention:** Always rely on FastAPI dependency injection to enforce endpoint security.

## 2024-05-28 - [Subprocess path execution vulnerability fix]
**Vulnerability:** [Bandit B607 Starting a process with a partial executable path and B603 subprocess call without shell equals true]
**Learning:** [Using partial paths with subprocess like 'bash' instead of absolute paths allows potential path manipulation attacks if PATH is altered. Executing python scripts with subprocess.run introduces process spawning overhead and could expose untrusted execution depending on how the interpreter executes inputs.]
**Prevention:** [Use shutil.which("bash") or absolute paths. For executing local python scripts from tests, use importlib to dynamically load the module and execute the target function directly instead of spawning a new python subprocess, which avoids B603 entirely and is generally more efficient.]

## 2026-06-20 - [Fix Subprocess Path Execution Vulnerability]
**Vulnerability:** B607: Starting a process with a partial executable path & B603: subprocess call without shell equals true.
**Learning:** Using `subprocess.run` with partial executable paths (like `"bash"`) could allow path injection attacks if the `PATH` environment variable is manipulated. Also calling local Python scripts using `subprocess` can be inefficient and triggers B603 warnings.
**Prevention:** Always use absolute paths (e.g. `shutil.which("bash")`) for external command execution. For local Python scripts, use `importlib` to dynamically import the module and invoke its `main()` function directly to avoid spawning new subprocesses.

## 2025-06-19 - Inconsistent Authorization in AI Hub

**Vulnerability:** The AI Hub's list prompts endpoint (`_list_prompts` in `backend/api/ai_hub.py`) strictly filtered returned prompts by `created_by == auth_context.user_id`, ignoring the `is_shared` property which allows a prompt to be accessed globally. This resulted in a failure of access control policies because shared resources were effectively hidden from the surface, while directly accessible through other APIs.
**Learning:** Authorization and resource filtering must be consistently scoped across the system. Inconsistency leads to functional security bugs where visibility does not match explicit intent (e.g. sharing).
**Prevention:** Unify queries regarding scoping (e.g., using centralized helper functions for where-clauses) instead of redefining conditions per-endpoint. When creating models with boolean overrides for visibility like `is_shared`, ensure all read paths respect them.

## 2024-05-31 - Hardcoded Session Token in Tests
**Vulnerability:** Found hardcoded string `"header.payload.signature"` in multiple `.test.ts` files.
**Learning:** Even in test files, realistic-looking hardcoded tokens or secrets can be flagged by security scanners as hardcoded credentials. It is bad hygiene.
**Prevention:** Use explicitly fake and descriptive placeholder strings like `"test-header.test-payload.test-signature"` for token mocking in tests.

## 2026-06-20 - Hardcoded API Key for Testing
**Vulnerability:** Hardcoded API keys and passwords were found in `backend/tests/test_tenant_config_model.py` and `backend/tests/test_email_client_smtp.py`.
**Learning:** Hardcoded secrets in testing files can still leak into version control and potentially be used in production or misconfigured systems.
**Prevention:** Avoid hardcoding any secrets, even in test files. Use environment variables with default fallback values (e.g. `os.environ.get("TEST_KEY", "dummy-value")`).
## 2026-06-20 - [Fix CSRF Default-Allow Bypass]
**Vulnerability:** The API proxy's `sameOriginStateChangingRequest` function previously allowed state-changing requests if both `sec-fetch-site` and `origin` headers were missing, creating a potential CSRF vector if an attacker suppressed the Origin header.
**Learning:** Default-allow fallbacks for missing security metadata can silently bypass critical protections, especially when relying solely on cookie-based authentication.
**Prevention:** Always fail securely by defaulting to `false` when required origin/referer security metadata is absent, ensuring strict enforcement for state-changing operations.
## 2026-06-24 - Prevent URL-Encoded and Windows Path Traversal Bypass

**Vulnerability:** Path traversal in `_dav_path_owner_user_id` could be bypassed using doubly URL-encoded sequences (for example, `%252e%252e%252f`) and Windows-style backslashes.
**Learning:** Checking for traversal sequences after a single `/` split is insufficient if the input path can contain encoded payloads or alternative path separators.
**Prevention:** Recursively unquote DAV paths until stable, standardize backslashes to forward slashes, and reject `.` or `..` path segments before extracting authorization scope.

## 2026-06-22 - [Bandit B314: Insecure XML Parsing in Tests]
**Vulnerability:** `xml.etree.ElementTree.fromstring` was used to parse XML responses in tests (`backend/tests/test_dav_api.py`), triggering Bandit B314 (vulnerable to XML attacks).
**Learning:** Even in test environments parsing trusted responses, standard XML parsers trigger security scanners because they are inherently vulnerable to XML external entity (XXE) and billion laughs attacks.
**Prevention:** Always use `defusedxml` (`import defusedxml.ElementTree as ET`) as a drop-in replacement when parsing XML anywhere in the codebase to pass static analysis and enforce secure-by-default habits.

## 2026-06-24 - Missing Auth Session Verification for OIDC
**Vulnerability:** Session metadata validation skipped explicit issuer (`iss`) and audience (`aud`) checks whenever OIDC was globally configured, rather than checking claims against the verifier that actually accepted the token.
**Learning:** Security validation functions must use contextual verifier evidence instead of assuming that a global configuration flag describes the token path.
**Prevention:** Pass the session verifier into metadata validation, fail closed when OIDC issuer/client configuration is incomplete, and normalize OIDC audiences before checking membership.

## 2026-06-25 - Incorrect UI Terminology Handling in Tests
**Vulnerability:** UI terminology mapping rules were not properly reflected in `EmailDetail.test.tsx`, meaning the test was passing incorrect english keywords like "Summary" and "Tasks" that shouldn't be exposed on the frontend.
**Learning:** We need to keep our assertions in sync with terminology rules from `AGENTS.md` and `docs/ui-ux/naruon-ui-ux-mapping.md`, replacing English terms with their Korean counterparts in assertions. Additionally, when writing new test cases, avoid copying existing state variables (like `container` and `root`) in testing files, and use the correct mocking setup. Ensure proper clean up for tests.
**Prevention:** Always verify terminology rules by running `grep` before committing changes to React components and related unit tests, enforcing localized text definitions.

## 2026-06-25 - [Fix Subprocess Path Execution Vulnerability in Tests]
**Vulnerability:** Found an instance of `shutil.which("bash")` being called directly inside a `subprocess.run` block rather than using the centralized `_bash_executable()` helper in `backend/tests/test_release_governance.py`. This could potentially mask issues if `shutil.which` returns `None` and triggers Bandit B607/B603.
**Learning:** Reusing shared, safe helper functions like `_bash_executable()` ensures that external command execution is always bound to absolute paths and handles `None` cases properly, mitigating path injection risks.
**Prevention:** Always refactor redundant `subprocess.run` blocks to use established helper methods that enforce absolute paths and perform necessary existence assertions.

## 2026-06-25 - [DAV Authorization Path Denial of Service]
**Vulnerability:** Unbounded `while True` loop in `_normalize_dav_authorization_path` during URL decoding could potentially lead to algorithmic complexity or infinite loop DoS if an unquote edge case prevented string convergence.
**Learning:** Although `unquote` generally guarantees termination (as the string length strictly decreases or stays the same), relying on external library invariants for loop termination without explicit bounds is poor security hygiene. Furthermore, simulating edge cases using objects fails because C-extensions validate parameter types.
**Prevention:** To mitigate algorithmic complexity (DoS) vulnerabilities when parsing inputs via `urllib.parse.unquote`, replace unbounded `while True:` decode loops with strictly bounded loops (e.g., `for _ in range(100):`) and explicitly raise exceptions (like `HTTPException`) if the limit is exceeded. When testing iteration limits or potential infinite loops involving `urllib.parse.unquote` in pytest, use `monkeypatch.setattr(module_name, "unquote", fake_unquote_function)` rather than attempting to pass fake Python objects (which are often ignored or converted by standard library C-extensions).

## 2026-06-27 - Information Disclosure in Version File Error Handling
**Vulnerability:** The error message generated when the `VERSION` file was missing included absolute paths, exposing the internal directory structure.
**Learning:** Error messages should never reveal internal implementation details or server-side paths, as they can assist attackers in further exploitation.
**Prevention:** Avoid interpolating absolute paths or system details into exceptions that might be logged or surfaced; use generic error messages instead.

## 2024-06-25 - [Fix Email SMTP CRLF Injection & Double Extension Upload]
**Vulnerability:** Attackers could inject arbitrary SMTP commands (e.g. MAIL FROM) using CRLF (\r\n) sequences in email subjects or recipients because `^[^\r\n]*$` validation in Pydantic wasn't catching all edge cases correctly. Attackers could also bypass file upload validations by providing double extensions (e.g., `malicious.exe.eml`).
**Learning:** Pydantic regex patterns might fall short for strict network protocol inputs like SMTP headers if improperly formulated or bypassed. Simple `.endswith()` checks for file uploads fail to prevent embedded dangerous extensions.
**Prevention:** Always use `@field_validator` with explicit `mode="before"` string matching for `chr(10)` and `chr(13)` across all user-controlled email header fields (to, subject, in_reply_to, references). Always tokenize uploaded filenames via `.split(".")` and reject if any segment matches a known dangerous extension (e.g., `.exe`, `.sh`).

## 2026-06-30 - JWT Algorithm Confusion
**Vulnerability:** JWT decoding remained allowlisted but static analysis could not prove the accepted algorithm when `jwt.decode(..., algorithms=...)` received module-level variables.
**Learning:** Security-sensitive decode boundaries should make accepted algorithms obvious to both runtime readers and static scanners.
**Prevention:** Pass explicit hardcoded lists such as `algorithms=["HS256"]` and `algorithms=["RS256"]` at the decode call sites, and keep header preflight checks aligned with those exact values.
## 2026-07-07 - URL-Encoded Open Redirect Bypass

**Vulnerability:** The `toSafeReturnTo` function in `frontend/src/app/auth/callback/page.tsx` validated paths to ensure they didn't start with double-slashes (`//`) or backslashes to prevent open redirects. However, attackers could bypass this validation by URL-encoding the payload (e.g. `/%5C%5Cexample.com` or `/%2fexample.com`).
**Learning:** Checking for traversal or open redirect payloads directly on raw URLs is insufficient, as the browser will decode and redirect to the encoded malicious payload anyway.
**Prevention:** Always decode the URI component (`decodeURIComponent`) and validate the decoded string to ensure that encoded bypass payloads are caught.
## 2025-02-20 - Webhook DNS Rebinding SSRF
**Vulnerability:** The webhook feature (`backend/api/tools.py`) validated that URLs resolved to safe global IP addresses using `validate_webhook_url`, but then created a fresh `httpx.AsyncClient` that performed its own independent DNS resolution at execution time. This Time-of-Check to Time-of-Use (TOCTOU) gap allowed an attacker to rapidly change DNS records after validation but before execution, causing the application to send requests to internal network services (Server-Side Request Forgery).
**Learning:** Checking hostnames or IPs before use is insufficient if the actual execution engine (HTTP client) resolves the hostname again. The underlying validation and execution must be perfectly coupled.
**Prevention:** Always pin the underlying HTTP transport to the exact IP addresses that were validated. This was achieved using the `ValidatedHTTPSURLHost` and `build_pinned_https_async_client` components which override the connection layer to use the pre-resolved, safe IPs.

## 2026-06-30 - XSS Vulnerability in DataLayout Component
**Vulnerability:** User-controlled input in file names and asset metadata was rendered without proper sanitization, allowing execution of arbitrary JavaScript (e.g. `<img src=x onerror=alert(1)>`).
**Learning:** React escapes text children by default, but relying on this is not enough if variables are passed to components that might render them unsafely, or if scanning tools mandate explicit sanitization functions for user-provided data.
**Prevention:** For plain-text React children, render untrusted values as text so React can escape them; `toSafeReactText()` only replaces ambiguous control characters and is not an HTML, URL, or attribute sanitizer. Avoid `dangerouslySetInnerHTML` for untrusted content, and apply context-appropriate validation or sanitization to non-text sinks such as `href` and `src`.

## 2026-07-15 - Prevent URL-Encoded Path Traversal in Email Import
**Vulnerability:** The `_safe_upload_filename` in `email_import_service.py` checked for path traversals (like `..`) without unquoting the filename first. This allowed an attacker to bypass the validation by URL-encoding or doubly URL-encoding the payload (e.g., `%2e%2e%2fupload` or `%252e%252e%252fupload`).
**Learning:** Checking for traversal sequences on raw filenames is insufficient if the input path can contain URL-encoded payloads. The check could be bypassed since it happens before decoding, yet the application or storage mechanism may later decode and use the dangerous payload.
**Prevention:** Always recursively decode `urllib.parse.unquote()` on raw input paths before validating, splitting, or extracting filenames to ensure doubly URL-encoded payloads are correctly decoded and caught, with a bounded loop to avoid DoS.

## 2026-07-22 - Prevent Path Traversal via Backslashes
**Vulnerability:** The `_safe_upload_filename` in `email_import_service.py` checked for path traversals (like `..`) but did not convert backslashes (`\`) to forward slashes (`/`), meaning that Windows-style path traversal attacks (like `..\..\upload` or encoded versions) could bypass the check.
**Learning:** Checking for traversal sequences using `pathlib.Path.name` may leave the result vulnerable if the input path can contain Windows-style path separators but the program interprets it dynamically or decodes payloads using backslashes.
**Prevention:** Always convert backslashes to forward slashes before parsing filenames.

## 2026-07-29 - Prevent SSRF via Local/Internal Domains
**Vulnerability:** The URL validation logic correctly blocked non-global IP addresses and `localhost`, but failed to block internal domain extensions such as `.internal` or `.local` (or exact matches for `internal`). This could allow attackers to bypass SSRF protections by resolving these internal top-level domains.
**Learning:** Checking for `localhost` alone is insufficient to prevent SSRF against internal network resources, as modern environments and protocols utilize `.internal` and `.local` domains for internal routing.
**Prevention:** Always explicitly check and block domains matching `.internal`, `.local`, or `internal` (alongside `localhost`) when validating URLs for global reachability to prevent SSRF bypasses.
## 2025-02-23 - CRLF Injection in Email Headers
**Vulnerability:** The `in_reply_to` and `references` fields on the `SendEmailRequest` model lacked explicit validation, opening up an opportunity for header injection by appending `\r\n`.
**Learning:** While the email service internally checks some headers, relying on the API boundary's Pydantic model ensures bad input is stopped early and consistently. Pydantic regex patterns aren't sufficient on their own for all string contexts due to encoding/decoding inconsistencies.
**Prevention:** Always use `@field_validator` with explicit `mode="before"` string matching to reject `chr(10)` and `chr(13)` across all user-controlled email header fields. Use `isinstance(value, str)` before string operations to prevent runtime errors if input is missing or malformed.

## 2026-08-05 - [Prevent Path Traversal via Backslashes in Attachment Parser]
**Vulnerability:** The `_safe_filename` function in `backend/services/attachment_parser.py` used `pathlib.Path().name` to strip directory components from attachment filenames, but failed to normalize backslashes beforehand. This allowed attackers to use Windows-style path separators (e.g., `..\..\upload`) to bypass path validation on POSIX systems.
**Learning:** Checking for traversal sequences using `pathlib.Path().name` may leave the result vulnerable if the input path can contain Windows-style path separators but the program interprets it dynamically or decodes payloads using backslashes, because POSIX `pathlib` treats backslashes as valid filename characters, not separators.
**Prevention:** Always convert backslashes to forward slashes before parsing filenames using `pathlib.Path().name`.
