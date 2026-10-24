# API: AI Personal Content Strategist

Status: Draft v1.1, under review
Scope: REST API between the React UI and the FastAPI backend.
Field-level schemas are written as Pydantic models during task API-00 and must match this document.

---

## 1. Conventions

- Base path: `/api/v1`. JSON request and response bodies. All routes below are relative to the base path.
- Single user, no login in v1. The backend binds to loopback only (`127.0.0.1`). See SECURITY.md.
- IDs are UUID strings. Timestamps are UTC ISO 8601.
- Long operations return `202 Accepted` with a `run_id`. The UI polls for status.
- Polling: every 2 seconds for the first minute, then every 5 seconds.
- List endpoints accept `limit` (default 20, max 100) and `cursor`.
- Errors use one shape:

```json
{ "error": { "code": "RUN_NOT_FOUND", "message": "Run not found.", "details": {} } }
```

- Status codes: 200 OK, 201 Created, 202 Accepted, 400 invalid input, 403 origin not allowed, 404 not found, 409 invalid state, 422 validation error, 500 server error.
- Error messages never include stack traces, file paths, tokens or third-party content.

### Local API protections

A malicious web page can make a browser send requests to a local server, so loopback binding alone is not enough.

- CORS allows only the configured frontend origin (`FRONTEND_ORIGIN`, default `http://localhost:5173`). No wildcard origin, and credentialed CORS is not used. CORS is not treated as authentication.
- Every `POST`, `PUT` and `DELETE` request must carry an `Origin` header equal to the allowed origin and `Content-Type: application/json`. Otherwise the response is 403 `ORIGIN_NOT_ALLOWED`.
- The `Host` header must be `localhost` or `127.0.0.1` with the configured port, on every request including the OAuth callback. This blocks DNS rebinding.
- The OAuth callback is a `GET` browser navigation. It is exempt from the Origin and JSON content-type rules, which apply to state-changing requests, and it must pass the OAuth `state` check (section 7) and the Host check.
- These are separate protections. CORS, Origin checks and the OAuth `state` are not interchangeable.

### Common error codes

`RUN_NOT_FOUND`, `APPROVAL_NOT_FOUND`, `STALE_APPROVAL`, `STALE_VERSION`, `NOT_APPROVED`, `RUN_ACTIVE`, `RUN_NOT_RESUMABLE`, `CHECKS_FAILED`, `DELETION_IN_PROGRESS`, `ORIGIN_NOT_ALLOWED`, `OAUTH_STATE_INVALID`, `OAUTH_SCOPE_MISMATCH`, `OAUTH_DENIED`, `CONFIRMATION_MISMATCH`, `ONBOARDING_REQUIRED`, `ONBOARDING_INCOMPLETE`, `CHANNEL_IDENTIFIER_INVALID`, `CHANNEL_NOT_FOUND`, `OAUTH_NOT_CONNECTED`.

---

## 2. Runs

### POST /runs
Start a run from a goal.
- Body: `goal_text` (string, required), `depth_level` (`quick`, `standard`, `deep`, optional, default from settings).
- Returns 409 `ONBOARDING_REQUIRED` until onboarding is completed (section 7). The same applies to manual brief creation.
- Response 202: `run_id`, `status`.
- 422 if the goal is empty. 409 `DELETION_IN_PROGRESS` while creator data is being deleted. 409 `RUN_ACTIVE` if another goal run is `RUNNING` or `WAITING_APPROVAL`. An `INTERRUPTED` run does not count as active.

### GET /runs
List runs, newest first. Filter by `status` and `run_type`.

### GET /runs/{run_id}
Run status and summary.
- Fields: `id`, `run_type`, `depth_level`, `status`, `step_count`, `tokens_used`, `stop_reason`, `degraded`, `degraded_reason`, `current_node`, `tasks` (list), `pending_approval_id` (nullable), `started_at`, `finished_at`.

### GET /runs/{run_id}/routing-log
Ordered routing decisions: `step_number`, `from_node`, `to_node`, `reason`, `decided_by`, `eligible_nodes`, `output_status`, `invalid_category`, `tokens_in`, `tokens_out`.

### POST /runs/{run_id}/cancel
Stop a running, waiting or interrupted run. Cancellation is cooperative: the run stops at the next step boundary. A tool call already in progress finishes or times out, its result is discarded, and no further writes happen. Pending approvals of the run become `CANCELLED`. 409 if already finished.

### POST /runs/{run_id}/resume
Resume an `INTERRUPTED` run from its last checkpoint. Tasks already `DONE` are not repeated. 409 `RUN_NOT_RESUMABLE` for any other status.

---

## 3. Approvals

### GET /approvals
List approval requests. Filter by `status` (`PENDING`, `DECIDED`, `CANCELLED`) and `item_type` (`plan`, `draft`, `depth_increase`).

### GET /approvals/{approval_id}
One request with the exact item to review: plan version with items, draft version with Critic notes, or a depth increase proposal with its reason. For a plan that belongs to a Weekly Brief, the response includes the `brief_id`.

### POST /approvals/{approval_id}/decision
- Body: `item_id` (required, the exact version the creator reviewed), `decision` (`APPROVED`, `REJECTED`, `EDITED`), `feedback_text` (required for `REJECTED`), `edited_content` (required for `EDITED`).
- `EDITED` means approve with the creator's edits. For a draft, `edited_content` is the new text. For a plan, it is the full edited list of plan items. The backend runs the deterministic checks. If they pass, it creates a new version authored by the creator, approves it in the same transaction, and returns `resulting_item_id`. If they fail, it returns 422 `CHECKS_FAILED` with the reasons and changes nothing. The Critic is not run again.
- Response 200: updated approval, `resulting_item_id` (if any) and the resumed `run_id` (if any).
- 409 `STALE_APPROVAL` if the approval is already decided or cancelled, its item has been superseded, or `item_id` does not match.

If the approval belongs to a run, the run resumes in the background and the Supervisor receives the decision and feedback through shared state.

---

## 4. Plans and drafts

### GET /plans/{plan_id}
Plan version with its items: `item_key`, `topic`, `format`, `platform`, `objective`, `reason`, `source_type`, `source_ref`, `priority`, `status`. Also `version`, `lineage_id`, `is_latest`, and the `brief_id` if linked.

### POST /plans/{plan_id}/edit
Edit an approved or pending plan outside an approval decision.
- Body: `items` (full edited list), `expected_version`. Items that keep their `item_key` stay the same logical item. Items without an `item_key` are new.
- Creates a new version in `PENDING_APPROVAL`, marks the earlier version `SUPERSEDED` and creates a new approval request. 409 `STALE_VERSION` if `expected_version` is not the latest. Response 201 with `plan_id` and `approval_id`.

### GET /drafts
Filter by `status`, `platform`, `kind`, `plan_item_id`, `lineage_id`. Default view for the "Ready to post" list is `status=APPROVED` and `is_latest=true`.

### GET /drafts/{draft_id}
Draft version content, `version`, `lineage_id`, `is_latest`, `status`, Critic evaluation for this version, posted details, and any repurposed child drafts.

### GET /drafts/{draft_id}/versions
All versions of the draft's lineage, with `version`, `status`, `created_by`, `created_at`, and which version is approved or posted.

### POST /drafts/{draft_id}/edit
Edit a draft outside an approval decision, for example after it was approved.
- Body: `content`, `expected_version`.
- Runs the deterministic checks (422 `CHECKS_FAILED` on failure). Creates a new version in `PENDING_APPROVAL`, marks the earlier version `SUPERSEDED` (its approval is no longer valid for the new text) and creates a new approval request. 409 `STALE_VERSION` if `expected_version` is not the latest. Response 201 with `draft_id` and `approval_id`.

### POST /drafts/{draft_id}/mark-posted
- Body: `posted_url` (optional), `platform_content_id` (optional), `posted_at` (optional, default now).
- Allowed only when this version is `APPROVED` and is the latest version. Otherwise 409 `NOT_APPROVED` or `STALE_VERSION`.
- Records this exact version as `POSTED`. If neither a URL nor an ID is given, the draft is posted but unlinked: `posted_ref = none`.
- Response includes `analytics_eligible` (true only when a URL or ID is present).

### POST /drafts/{draft_id}/link-posted
Add a URL or platform ID to a posted but unlinked draft.
- Body: `posted_url` or `platform_content_id`. Only allowed when status is `POSTED`. This is the only change a posted draft accepts. Makes it eligible for analysis.

### POST /drafts/{draft_id}/repurpose
Ask for repurposed versions of an approved draft.
- Body: `targets` (list of `youtube_short`, `community_post`, `description`, `instagram_caption`, `linkedin_post`, `x_thread`).
- Response 202 with `run_id`. 409 `NOT_APPROVED` if the draft is not an approved latest version.

---

## 5. Weekly Briefs

### GET /briefs
List briefs, newest first, with `trigger` (`scheduled` or `manual`), `status` and `read_at`.

### GET /briefs/{brief_id}
Brief content in Markdown, and the linked plan (with its own status and approval) if any.

### POST /briefs/run
Run a brief now, outside the schedule. Creates a `manual` brief. Manual briefs do not count toward the scheduled brief for that week and never block it. Response 202 with `run_id`. 409 `RUN_ACTIVE` if a brief run is already active.

### POST /briefs/{brief_id}/mark-read
Sets `read_at`.

Scheduling behavior is defined in ARCHITECTURE.md section 9.

---

## 6. Insights and strategy

### GET /insights/comments
Current comment insights: `theme_label`, `comment_count`, `examples`, `coverage_analyzed`, `coverage_total`. Only insights that pass the channel rule are returned. Each example is read from its comment and is returned as unavailable once the comment text has been cleared (90 days).

### GET /findings
Analyst findings: `finding`, `recommendation`, `confidence`, `sample_size`, linked draft.

### GET /strategy
Active strategy entries with the reason for each and the findings that support it. Add `?include=history` for superseded entries.

---

## 7. Settings, credentials and creator data

### GET /settings and PUT /settings
- Fields: `default_depth_level`, `brief_day` (default `mon`), `brief_time` (`HH:MM`, default `08:00`), `time_zone` (IANA name, default `Asia/Kolkata`), `niche`, `tone_preset`, `tone_instructions`. The response also includes `onboarding_completed`, which is read-only here.
- `PUT /settings` accepts a partial body. Omitted fields are unchanged. Onboarding saves each step through it.
- Validation is server-side and returns 422 with the field names in `details`: `niche` is trimmed and must be 1 to 200 characters. `tone_preset` must be one of `professional`, `friendly`, `educational`, `conversational`, `humorous`. `tone_instructions` is trimmed and may be empty, up to 500 characters. Control characters are rejected, except newlines in `tone_instructions`.
- Niche and tone text is untrusted data when it reaches a prompt (RULES.md section 4).
- Defaults come from the environment only when no saved value exists. Saved settings always win.
- Changing `brief_day`, `brief_time` or `time_zone` reschedules the Weekly Brief job before the response is returned. The response includes `next_brief_at`. An invalid time zone returns 422.
- Before onboarding is completed, a schedule change is only saved. No job is created or replaced, and `next_brief_at` is `null`. `POST /onboarding/complete` creates the job from the saved values. After completion, a change replaces the existing job.

### Onboarding and channel

Subject to the Origin and JSON rules for every `POST`, `PUT` and `DELETE`.

- **GET /onboarding**: `{ "onboarding_completed": false, "next_step": "niche" | "tone" | "channel" | "review", "values": { "niche", "tone_preset", "tone_instructions", "channel": { "channel_id", "handle", "title", "verified" } or null, "api_key_configured": true, "youtube_oauth": { "state": "disconnected" } } }`. `next_step` is `niche` or `tone` while those are missing. Once both are saved it is `channel`, unless a channel is saved or the creator skipped the step (`onboarding_channel_skipped`), in which case it is `review`. It never returns a secret. It does not include the Weekly Brief schedule. The review step reads `brief_day`, `brief_time` and `time_zone` from `GET /settings`.
- **POST /onboarding/skip-channel**: no body. Saves `onboarding_channel_skipped = true` on the server, so the skip survives a restart or reopening the app. Idempotent. Needs niche and tone saved, otherwise 409 `ONBOARDING_INCOMPLETE`. The creator can still add a channel later from the review step or Settings.
- **POST /onboarding/complete**: no body. Needs `niche` and `tone_preset` saved, otherwise 409 `ONBOARDING_INCOMPLETE` with the missing fields in `details`. Sets `onboarding_completed`, calls the scheduler service, which creates the Weekly Brief job from the saved settings (environment defaults seed the schedule if none is saved) and returns `{ "onboarding_completed": true, "next_brief_at": "..." }`. Idempotent. It never starts a run.
- Until onboarding is completed, `POST /runs` and manual brief creation return 409 `ONBOARDING_REQUIRED`, and the scheduler has no job and the startup catch-up generates nothing.
- **POST /channel/resolve**: body `identifier`. Accepted forms: `@handle`, a channel ID (`UC` followed by 22 URL-safe characters) and `https://youtube.com/@handle` or `https://youtube.com/channel/<ID>` (with `www.` or `m.`). The string is parsed locally against these forms, never fetched, and any other form, host or scheme returns 422 `CHANNEL_IDENTIFIER_INVALID` before any network call.
  - Key configured and channel found: `{ "resolved": true, "channel_id": "UC...", "title": "..." }`. Not found: 404 `CHANNEL_NOT_FOUND`. Lookup failure or quota: `{ "resolved": false, "reason": "LOOKUP_FAILED" }`.
  - Key not configured: `{ "resolved": false, "reason": "API_KEY_NOT_CONFIGURED", "parsed": { "type": "handle" or "channel_id", "value": "..." } }`.
  - Saves nothing. It uses the YouTube Data API only. Handle lookup support is confirmed at MCP-01.
- **GET /creator/channels**: lists the channels of the connected YouTube login for the pick-list. Returns 409 `OAUTH_NOT_CONNECTED` unless the YouTube login state is `connected`.
- **PUT /creator/channel**: body with exactly one of `identifier` (same forms as resolve) or `oauth_channel_id`. With `identifier`, the server parses it, and if the key is configured resolves it and saves it as verified (404 `CHANNEL_NOT_FOUND` if it does not exist), otherwise saves the parsed value as unverified. With `oauth_channel_id`, the server checks the ID is in the connected account's list and saves it as verified. The client never sets `verified`. Returns `{ "channel_id", "handle", "title", "verified" }`.
- **DELETE /creator/channel**: clears the saved channel. Stored content is not touched (ADR-032). The same applies when `PUT /creator/channel` changes the channel. Insights from the previous channel stay stored but are excluded from current plans and analysis (DATABASE.md, channel rule).

### YouTube API key (no endpoint)
The public-data API key is set only in `.env` (`YOUTUBE_API_KEY`) and read through backend configuration at startup. In v1:
- No endpoint accepts, stores, replaces, deletes or returns the key.
- No endpoint returns the key, in whole or in part, including masked forms such as the last four characters.
- Changing the key means editing `.env` and restarting the backend.
- The key is not stored in the database.
- Managing the key through the API is planned for v2 (ADR-021).

### POST /auth/youtube/start
Creates a random, single-use `state` value (valid 10 minutes, stored hashed) and returns `{ "authorization_url": "..." }` with read-only scopes only. It is a POST because it creates server-side state.
- Body: `return_to` (`settings` or `onboarding`, default `settings`), stored with the `state`. Any other value returns 422. The post-callback redirect target comes only from this fixed list, never from a caller-supplied URL.

### GET /auth/youtube/callback
Full path: `/api/v1/auth/youtube/callback`. This exact URI is registered in the Google Cloud Console and set in `GOOGLE_OAUTH_REDIRECT_URI`. The handler:
- rejects a missing, unknown, expired or reused `state` (`OAUTH_STATE_INVALID`);
- handles `error=access_denied` and other provider errors without storing anything (`OAUTH_DENIED`);
- checks the granted scopes against the required read-only set, and discards the tokens if any scope is missing or any extra or write scope is granted (`OAUTH_SCOPE_MISMATCH`);
- stores only the encrypted refresh token, and keeps access tokens in memory;
- redirects to the UI page stored as `return_to` (`/settings` or `/onboarding`) as `?oauth=success`, `?oauth=denied` or `?oauth=error&reason=<code>`. No token, code or state value appears in any redirect URL, log or response.

### DELETE /credentials/{platform}
Disconnects `youtube` or `instagram`: deletes the stored refresh token, drops any in-memory access token and revokes the grant at the provider on a best-effort basis. It does not touch the API key, which lives in `.env`. Any other platform value returns 422.

### GET /credentials/status
Which credentials are present, never their values. Response shape:

```json
{
  "api_key": { "configured": true },
  "youtube_oauth": { "state": "connected" },
  "instagram": { "state": "disconnected" }
}
```

OAuth `state` is `connected`, `needs_reauth` or `disconnected`. `needs_reauth` is set when a refresh token is expired, revoked or invalid. Tools then return a structured `AUTH_EXPIRED` error, runs finish with partial results and the UI offers Reconnect. `api_key.configured` means the variable is set and non-empty. It does not prove the key is valid. Validity problems appear as structured tool errors during runs.

### DELETE /creator/data
Deletes all stored data for the creator.
- Body: `confirm_text` (must equal `DELETE MY DATA`, otherwise 422 `CONFIRMATION_MISMATCH`).
- Response 202: `deletion_job_id`. The job runs in the background.
- The job runs these steps in order and records the status of each: (1) stop active runs and refuse new runs and briefs with 409 `DELETION_IN_PROGRESS`; (2) delete local OAuth tokens, with provider revocation attempted on a best-effort basis, where a revocation failure is a warning and never blocks local deletion; (3) remove scheduler jobs; (4) delete checkpoints for the creator's `thread_id` values; (5) delete application rows; (6) delete cache entries; (7) compact both database files.
- Re-sending the request resumes the job from the failed step. The operation is idempotent.
- `.env` values, including the API key, are not creator data and are not removed.
- Evaluation results and the job record remain. They contain no creator content.

### GET /creator/data/deletion/{job_id}
Job status (`PENDING`, `RUNNING`, `COMPLETED`, `PARTIAL`, `FAILED`) with per-step results. The job is reported `COMPLETED` only when every step succeeded. If a step fails, the result is `PARTIAL`, names the failed steps, and the data of later steps is kept so the job can be retried. After `COMPLETED`, the normal APIs return no creator data.

---

## 8. Evaluation

### POST /evaluation/run
Run the fixed pipeline and the Supervisor graph on the test cases.
- Body: `test_case_ids` (optional, default all).
- Response 202 with `evaluation_run_id`.
- Both variants use the same model, tools, fixtures and settings, and the run records them (see DATABASE.md `evaluation_runs`).

### GET /evaluation/runs/{id}
Per-case results and averages for both variants, including `routing_invalid` and `routing_suboptimal`.

---

## 9. System

### GET /health
Backend status, database reachable, Ollama reachable, installed models present (`qwen3.5:4b`, embedding model), YouTube API key configured (true or false, never the value), scheduler running, next scheduled brief time, number of interrupted runs.

---

## 10. State rules

- A run in `WAITING_APPROVAL` has exactly one pending approval.
- A decision can only be sent once per approval, and only for the exact item version it was requested for.
- An approval request is cancelled when its item is superseded. A decision sent for it returns 409 `STALE_APPROVAL`, so a stale screen can never approve an obsolete version.
- A draft cannot be marked posted unless that exact version is `APPROVED` and is the latest version.
- Editing an approved item creates a new version that needs its own approval.
- Starting a goal run while another goal run is `RUNNING` or `WAITING_APPROVAL` returns 409 in v1, since one local model serves all runs.
- A depth increase proposal cannot be bypassed. The run does not continue at a higher depth without an `APPROVED` decision.
- At startup, runs left in `RUNNING` become `INTERRUPTED` and stay so until the creator resumes or cancels them.

---

## 11. Platform capabilities (v1)

| Platform | Draft generation | Public research data | Owner analytics | Credentials |
|---|---|---|---|---|
| YouTube | Yes | Yes, within API quota | Yes, where the API supports it | API key for public data. Read-only OAuth for owner metrics |
| Instagram | Yes | No | Optional, read-only, Business or Creator account | Optional OAuth |
| LinkedIn | Yes | No (web research only) | No | None |
| X | Yes | No (web research only) | No | None |

For LinkedIn and X, the Analyst reports that no performance data is available. Exact capabilities are confirmed by the MCP checks (MCP-01 to MCP-04) before implementation.

---

## 12. Open points

- Field-level Pydantic schemas (task API-00).
- Whether progress needs server-sent events later. Polling is used in v1.
- v2: endpoints to set, replace and remove the API key, with encrypted storage (V2-04, ADR-021).
