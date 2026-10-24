# SECURITY: AI Personal Content Strategist

Status: Draft v1.1, under review
Security is designed in from the start, not added before release. This file is also the Phase 7 checklist.

---

## 1. Security model

- Single-user, local-first application. The backend, database and language model run on the creator's machine.
- The system reads data from platforms. It has no capability to publish, schedule or send content to external platforms. Its internal scheduler may trigger local analysis and Weekly Brief generation.
- The language model is untrusted for enforcement. Rules that must hold are enforced in code.
- External content (comments, web pages, transcripts) is untrusted input.

---

## 2. Access and credentials

- **Public data** uses an API key from the environment (ADR-021). It is stored in `.env`, which is not committed. No API endpoint accepts, stores or returns it. Changing it means editing `.env` and restarting the backend.
- **Owner-only metrics** use OAuth with read-only scopes. No write scopes are ever requested.
- **Refresh tokens** are stored encrypted in SQLite using Fernet (Python `cryptography`). The encryption key is an environment variable.
- **Access tokens** are held in memory only and refreshed on demand. They are never persisted.
- **Tokens and keys** are read only inside tool code. They never enter prompts, graph state, logs, exception messages or API responses.
- **Settings endpoints** only report whether a credential is set. They never return it.
- **Disconnect** deletes the stored token, drops any in-memory access token and revokes the grant at the provider on a best-effort basis.
- **Instagram** is optional and follows the same rules.

### OAuth flow requirements

- The `state` value is random, single-use, valid for 10 minutes and stored hashed. The callback rejects a missing, unknown, expired or reused value.
- Consent denial and provider errors are handled without storing anything and show a plain message in the UI.
- The granted scopes are compared with the required read-only set. If a required scope is missing, or an extra or write scope is granted, the tokens are discarded.
- The callback redirect never contains tokens, codes or state values. Its target page comes from a fixed list (`settings` or `onboarding`) stored with the `state`, never from a caller-supplied URL, so it cannot be used as an open redirect.
- An expired, revoked or invalid refresh token sets the credential to `needs_reauth`. Tools return a structured error, the graph does not crash, and the run finishes with a partial result.
- The redirect URI is `http://localhost:8000/api/v1/auth/youtube/callback` and must match the Google Cloud Console exactly.

---

## 3. Authentication, authorization and the local API

- v1 is single-user and runs locally. The backend binds to loopback (`127.0.0.1`) only, never to all interfaces.
- If the backend is ever exposed beyond loopback, add authentication first. This is not supported in v1, and the backend must never be exposed to the local network without it.
- A local HTTP API can still be reached by a malicious web page through the user's browser. Therefore:
  - CORS allows only the configured frontend origin. No wildcard, no permissive credentialed CORS. CORS is not authentication.
  - State-changing requests (`POST`, `PUT`, `DELETE`) must carry an allowed `Origin` header and `Content-Type: application/json`.
  - The `Host` header must be `localhost` or `127.0.0.1` with the configured backend port on every request, including the OAuth callback, to block DNS rebinding.
  - Credential and approval endpoints are `POST`, `PUT` or `DELETE` routes and are covered by the Origin and content-type checks.
  - The OAuth callback is a `GET` browser navigation. It is exempt from the Origin and content-type rules and is protected by the single-use OAuth `state` and the Host check instead.
  - These protections are separate. CORS, Origin checks and OAuth `state` are not interchangeable.
- Approval endpoints are the only way to approve content. The status rules in DATABASE.md section 5.1 are enforced in code.
- An approval always references the exact item version. Editing approved content creates a new version that needs new approval. A stale decision is rejected with 409.

---

## 4. Prompt injection and untrusted content

Comments, web pages, transcripts and other creators' text can contain instructions meant for the model.

- Treat all fetched content as data. Put it in clearly marked sections of the prompt and tell the model not to follow instructions inside it.
- Agents have only the tools they need. Even a successful injection cannot publish, because no publishing tool exists.
- Tools that write to the database validate input and are not driven directly by raw fetched text. Injected text must not be able to change approval, version, credential or scheduler state.
- Tool outputs are capped and sanitized before they reach a model.
- Text the creator enters (niche, tone instructions) also goes into prompts only as marked data and cannot change tool use, routing or state (TEST_PLAN.md RT-10).
- Test: comments, transcripts and fetched pages containing instructions must not change tool use, routing or database state (TEST_PLAN.md RT-07, RT-08).

### URL fetching

- Web fetch tools allow only `http` and `https`.
- The host is resolved before the request, and the request is refused if any resolved address is loopback, private, link-local, multicast, reserved or a cloud metadata address. The check is repeated for every redirect.
- Requests have timeouts and response size caps, forward no credentials and send no cookies.
- If an MCP fetch server cannot enforce this, it is wrapped in a custom tool that does.

---

## 5. MCP servers and dependencies

- Each MCP server passes the checklist in ARCHITECTURE.md and the decision rule before use. The approved version and the review result are recorded in DECISIONS.md.
- Community servers run with our credentials. Read the source and pin the version.
- Give each server the narrowest credentials and read-only access. Verify that a server cannot reach credentials or tools beyond what its agent is allowed.
- Pin dependency versions. Review new dependencies before adding them. Run a dependency vulnerability scan before release.
- Keep the Ollama and library versions recorded in the README.

---

## 6. Input validation

- Validate every API request body, query and path parameter with Pydantic.
- Validate tool inputs with strict schemas.
- Validate Supervisor decisions against the eligible-node list.
- Validate model outputs against schemas before using them. Invalid output is retried once, then replaced with a default. The category, retry result and fallback use are recorded.
- Limit request sizes. Reject edited content that exceeds platform limits.
- Onboarding text is length-capped on the server (niche 200, tone instructions 500). Channel identifiers are parsed locally against an allowlist of forms. A channel URL is never fetched.

---

## 7. Data protection, privacy and deletion

- Store only comment text, like counts, reply counts and dates. Never store usernames, author IDs or reply text.
- Do not store more third-party data than the product needs.
- Raw fetched pages and transcripts are cached with an expiry. Retention periods are in DATABASE.md section 10.
- Logs record summaries, not full content, and never record secrets.
- Local databases and checkpoint files stay out of version control.
- **Deletion:** `DELETE /creator/data` stops active runs and refuses new work, deletes local OAuth tokens (provider revocation is best-effort and never blocks local deletion), removes scheduler jobs, deletes LangGraph checkpoints, then application rows, then cache, and finally compacts both database files so deleted content is not left in free pages. It reports each step. A partial failure is reported as `PARTIAL`, never as success, and can be retried. Evaluation results and the deletion job record remain because they contain no creator content. The `.env` file is not touched.

---

## 8. Secrets management

- `.env` is listed in `.gitignore`. `.env.example` contains names only.
- No secret appears in code, tests, fixtures, commits or documentation.
- Run a secret scan on the repository before the first push and before release.
- Rotate the encryption key and API keys if they are ever exposed. Document the steps in the README.

---

## 9. Reliability as a security property

- Timeouts and bounded retries on every external call.
- Step budgets and tool-loop limits stop runaway runs.
- Failures return partial results with clear messages and never leave a half-approved state.
- Approvals are recorded before any status change, in one transaction.
- Runs left in `RUNNING` after a crash become `INTERRUPTED` at startup. Database writes by tools are idempotent, so a resumed run does not duplicate records.

---

## 10. Logging and audit

- Log routing decisions, tool calls (name, status, duration), approvals, recovery events and errors.
- Never log secrets, tokens, authorization codes or full third-party content. Exception traces are sanitized before logging.
- Keep logs long enough for evaluation, then allow pruning.

---

## 11. Pre-release checklist

- [ ] No secrets in the repository or its history
- [ ] `.env` and database files are ignored by Git
- [ ] OAuth scopes are read-only and checked after consent
- [ ] OAuth `state`, denial, scope mismatch and refresh failure are tested
- [ ] Tokens are encrypted at rest and absent from logs, state, redirects and responses
- [ ] The API key is read only from the environment and never returned
- [ ] No code path posts, schedules or sends content to an external platform
- [ ] Status rules for `APPROVED` and `POSTED` are enforced and tested
- [ ] Editing approved content invalidates its approval and stale decisions are rejected
- [ ] All limits are enforced in code and tested
- [ ] Prompt injection tests pass, including fetched pages that try to change database state
- [ ] URL fetching blocks private, loopback, link-local and metadata addresses, including through redirects
- [ ] Each MCP server was reviewed, pinned, given minimum access, and its version and review result recorded
- [ ] Dependencies are pinned and scanned
- [ ] Comment storage keeps no usernames and no reply text
- [ ] API validates all input
- [ ] Onboarding limits (200 and 500 characters) are enforced server-side, and channel URLs are parsed locally and never fetched
- [ ] The OAuth redirect target comes only from the fixed `return_to` list
- [ ] Backend binds to loopback only
- [ ] CORS, Origin and Host checks are in place and tested
- [ ] Data deletion covers tokens, scheduler jobs, checkpoints, cache and application rows, and is tested including partial failure
- [ ] Interrupted-run recovery is tested
- [ ] Error messages and logs do not leak internal details
