# TASKS: AI Personal Content Strategist

Status: Draft v1.1, under review
Work on one task at a time: understand, plan, implement, test, review, commit, update documents.
Each task ID is used in commit messages. Mark a task complete only when its tests pass.

---

## Phase 0: Setup and spec lock

- [x] SET-01 Create the repository, `.gitignore`, `.env.example` and the `docs/` folder
- [x] SET-02 Set up the backend project (Python, FastAPI, Ruff, mypy, pytest)
- [x] SET-03 Set up the frontend project (React, TypeScript, lint, tests)
- [ ] SET-04 Install Ollama and pull `qwen3.5:4b` and the embedding model (default `nomic-embed-text`; confirm the exact name, set `EMBEDDING_MODEL`, and record it in DECISIONS.md)
- [ ] SET-05 Add a health check that confirms the database, Ollama and both models
- [ ] API-00 Write field-level Pydantic schemas that match API.md
- [ ] DOC-01 Review all documents for consistency
- [ ] DOC-02 Spec-lock gate: freeze PRD, ARCHITECTURE, DATABASE and API before Phase 1
- [x] DEC-01 Decide API-key storage: environment only in v1, UI-managed in v2 (ADR-021)
- [x] DOC-05 Decide versioning, scheduling, deletion, platform scope, recovery and local-API rules (ADR-022 to ADR-028) and update the documents
- [x] DOC-06 Add the first-run onboarding flow (PRD FR-0 and DESIGN 4.0: niche, tone, optional channel by handle or OAuth pick-list, review) to PRD.md and DESIGN.md. Done. ADR-030, ADR-031 and ADR-032 accepted on 2026-10-24
- [ ] DOC-07 Final consistency check of all documents against ADR-021 to ADR-033 before DOC-02, including the onboarding, channel and comment-retention changes to PRD, DESIGN, DATABASE, API, SECURITY and TEST_PLAN
- [x] DOC-08 Owner decision on every Proposed ADR that other documents already assumed: ADR-007, ADR-010, ADR-013, ADR-015, ADR-019, ADR-030, ADR-031, ADR-032 and ADR-033. All accepted on 2026-10-24, recorded in DECISIONS.md. Conditions: review ADR-015 limits after MODEL-01, revisit channel-handle resolution after MCP-01
- [ ] MODEL-01 Test `qwen3.5:4b` on tool selection, no-tool precision, routing decisions and structured output; record results in DECISIONS.md. Then review the ADR-015 depth levels and token limits against the results
- [ ] MCP-01 Check the YouTube MCP server with the ARCHITECTURE.md checklist and apply the decision rule. Confirm channel lookup by handle and revisit channel-handle resolution (ADR-031)
- [ ] MCP-02 Check the web search and web fetch MCP servers
- [ ] MCP-03 Check the Instagram MCP server (optional, read-only)
- [ ] MCP-04 Check how transcripts can be obtained for (a) other creators' videos and (b) the connected creator's own videos, including the OAuth scopes caption download needs and whether they fit the read-only rule (ADR-009)
- [ ] MCP-05 Record a pass or fail for every checklist item (including failure behavior, provenance, permission boundaries and credential isolation) for each server in the DECISIONS.md results log
- [ ] DATA-01 Collect sample creator data (videos, comments, public stats) for testing

---

## Phase 1: Thin agentic core

Goal: a working agentic loop where the route depends on state, including a rejected-plan path.

- [ ] DB-01 Create SQLAlchemy models and Alembic migrations for the tables needed in Phase 1, including plan lineage and versions, approvals with exact item IDs, and the `INTERRUPTED` run status. Also create `creators` and `settings` (onboarding fields) here, because onboarding is the first screen, and the comment tables with nullable `text`, `comment_insight_sources` and `comment_insight_examples`
- [ ] DB-02 Set SQLite options (foreign keys, WAL) and add repository functions
- [ ] GRAPH-01 Define the graph state and the Pydantic decision models
- [ ] GRAPH-02 Build the Supervisor: eligible-node calculation in code, model choice, validation, default fallback
- [ ] GRAPH-03 Add the step budget, repeat detection and the routing log
- [ ] GRAPH-04 Add the SQLite checkpointer in its own database file
- [ ] SCHED-00 Scheduler service (APScheduler with the SQLAlchemy job store): create, remove and replace the Weekly Brief job from saved settings. It creates no job until onboarding is completed. Its target is a placeholder that does nothing until the brief exists (AGT-07). Called by `POST /onboarding/complete` and by schedule changes
- [ ] TOOL-01 Build the comment fetcher (cap, filters, coverage count)
- [ ] TOOL-02 Build the comment clusterer with local embeddings
- [ ] TOOL-03 Build the state and database tools
- [ ] TOOL-04 Load approved MCP servers through the MCP adapter, with per-agent allowlists
- [ ] TOOL-07 Build the URL guard for fetch tools (http and https only, block private, loopback, link-local and metadata addresses before and after redirects, time and size caps)
- [ ] AGT-01 Build the Listener agent (ReAct)
- [ ] AGT-02 Build the Research agent (ReAct)
- [ ] AGT-03 Build the Strategist agent with plan items and source labels
- [ ] HITL-01 Build the approval node with LangGraph interrupt and the approval tool
- [ ] HITL-02 Resume a paused run after a backend restart
- [ ] API-01 Implement runs endpoints
- [ ] API-02 Implement approvals endpoints
- [ ] BG-01 Run graphs in a background worker with status updates and cooperative cancellation
- [ ] REC-01 Recover runs at startup: `RUNNING` becomes `INTERRUPTED`, record a recovery event, add resume, keep pending approvals, make tool writes idempotent
- [ ] VER-01 Plan versioning: lineage, immutable versions, exact-version approvals, `EDITED` and stale-decision handling, cancelled approvals
- [ ] SEC-03 Add CORS for one origin, Origin and Host checks, and the JSON-only rule for state-changing requests
- [ ] UI-01 Build the app shell, sidebar and API client
- [ ] UI-02 Build the Home screen with the goal box and depth selector
- [ ] UI-03 Build the Approvals inbox and plan review screen
- [ ] ONB-01 Onboarding backend: settings fields (`niche`, `tone_preset`, `tone_instructions`, `onboarding_channel_skipped`, `onboarding_completed`) with server-side validation (200 and 500 characters, control characters) through a partial `PUT /settings`. `GET /onboarding`, `POST /onboarding/skip-channel`, `POST /onboarding/complete` (calls SCHED-00), `POST /channel/resolve` with local identifier parsing, and `PUT` and `DELETE /creator/channel`. The `creators` row is created at the first save. Runs and manual briefs return 409 `ONBOARDING_REQUIRED` until completed. Channel changes keep stored content (ADR-032)
- [ ] ONB-02 Onboarding UI (DESIGN 4.0: niche, tone, channel by handle, skip, review), with per-step saves, resume (including resuming at Review after a skip), and loading, empty and error states
- [ ] PROF-01 Build the creator-profile object in code from settings (declared fields only, `profile_source = "declared"`) and pass it to the Writer and Critic inside the marked untrusted-data section of the prompt
- [ ] TEST-01 Test routes for new creator, established creator and rejected plan, plus plan edit, stale approval, recovery, cancel during a tool call, Origin and Host checks, and the URL guard
- [ ] TEST-07 Test failure paths: invalid Supervisor JSON, repeated invalid tool arguments, unavailable MCP server, structured tool errors, Ollama unavailable during a run, budget reached while waiting, and the degraded-run indicator
- [ ] TEST-08 Run UT-32 (tool allowlists and provenance), UT-33 (MCP permission boundaries) and RT-09 (planted secret unreachable through an MCP server), plus the onboarding and channel tests UT-34 to UT-36, UT-38, UT-39, RT-10 and E2E-16

---

## Phase 2: Writer and Critic loop

Goal: controlled iteration that improves draft quality.

- [ ] AGT-04 Build the Writer agent for scripts, titles, descriptions and posts
- [ ] TOOL-05 Build the draft checker
- [ ] AGT-05 Build the Critic with rubric scoring, structured feedback and the review limit
- [ ] GRAPH-05 Add the Writer to Critic loop and best-draft selection
- [ ] DB-03 Add drafts (with lineage, versions and posted reference) and critic_evaluations
- [ ] VER-02 Draft versioning: every edit or revision creates a version, approval ties to the exact version, editing approved content invalidates the approval, creator edits run the deterministic checks only, mark-as-posted records the approved version
- [ ] API-03 Implement plans and drafts endpoints, including edit, versions, mark-posted and stale-version errors
- [ ] UI-04 Build the Draft review screen with the Critic panel
- [ ] UI-05 Add the Copy and Mark as posted actions
- [ ] TEST-02 Test the revision loop, the retry limit, the exhausted-limit banner, editing before and after approval, and marking an unapproved or outdated version as posted

---

## Phase 3: Goal decomposition and replanning

Goal: different goals and starting states produce different routes without hardcoded workflows.

- [ ] GRAPH-06 Add task list creation and replanning to the Supervisor
- [ ] GRAPH-07 Add skip and repeat logic based on data freshness
- [ ] GRAPH-08 Add depth levels and enforcement of all limits
- [ ] GRAPH-09 Add the depth increase proposal and its approval
- [ ] UI-06 Build the Runs history and the routing log timeline
- [ ] TEST-03 Test thin data, stale data, limit reached and depth increase

---

## Phase 4: Post-Mortem Analyst and strategy memory

Goal: close the feedback loop.

- [ ] DB-04 Add performance_metrics, analyst_findings and strategy_entries
- [ ] TOOL-06 Build the metrics calculator
- [ ] AGT-06 Build the Post-Mortem Analyst (ReAct) with sample size and confidence
- [ ] GRAPH-10 Route Analyst findings to the Strategist and store strategy changes
- [ ] API-04 Implement insights, findings and strategy endpoints
- [ ] UI-07 Build the Insights screen
- [ ] API-07 Implement link-posted and make the Analyst skip unlinked posts with a clear message, matching by URL or platform ID and never by title
- [ ] TEST-04 Test that findings change the next plan, and that unlinked posts produce no misleading analytics
- [ ] STYLE-01 Deferred: observed-style analysis of the creator's content. Blocked until MODEL-01, MCP-04 and the stored-profile decision in ADR-030 are complete

---

## Phase 5: Weekly Brief, scheduler and credentials

Goal: a recurring deliverable that adapts to what changed.

- [ ] DB-05 Add weekly_briefs (with `trigger`, `period_key` and the partial unique index), oauth_states (with `return_to`) and deletion_jobs. The `settings` table is created earlier, in DB-01
- [ ] AGT-07 Add the brief mode to the Writer and brief assembly to the Supervisor, with skip logic
- [ ] SCHED-01 Connect the SCHED-00 job to brief generation (AGT-07) and verify the configurable weekly trigger end to end (default Monday 08:00, Asia/Kolkata)
- [ ] SCHED-02 Add the startup catch-up check (latest overdue scheduled brief only) and duplicate protection through `period_key`. The catch-up generates nothing before onboarding is completed
- [ ] SCHED-03 Harden schedule changes: skip overlapping triggers and handle time-zone and daylight-saving changes (basic job replacement is in SCHED-00)
- [ ] CRED-01 Read the YouTube API key from `.env` through backend config. Never accept or return it through the API or store it in the database. Report only configured or not configured. Return a structured tool error when it is missing
- [ ] CRED-02 Add read-only OAuth, encrypted refresh-token storage and in-memory access tokens
- [ ] CRED-03 Complete the OAuth contract: single-use state, consent denial, scope check, refresh failure to `needs_reauth`, disconnect with revoke, no tokens in redirects or logs, callback at `/api/v1/auth/youtube/callback`
- [ ] ONB-03 Onboarding with YouTube login: `return_to` on OAuth start, `GET /creator/channels` pick-list, and onboarding after data deletion. Tests: UT-37 and E2E-17
- [ ] DEL-01 Build the creator data deletion service with these ordered steps: stop active runs and refuse new work, delete local tokens (best-effort revocation that never blocks), remove scheduler jobs, delete checkpoints, delete application rows, delete cache, compact both databases. Record each step and support retry from the failed step
- [ ] DEL-02 Add the deletion endpoints and the Settings danger zone with typed confirmation
- [ ] RET-01 Add the cleanup job (startup and daily) for comments, insights, cache, transcripts, run events and OAuth states
- [ ] API-05 Implement briefs, schedule settings and credentials status endpoints (the onboarding settings fields and endpoints are already built in ONB-01) (no endpoint accepts or returns the API key)
- [ ] UI-08 Build the Briefs screens and the Settings screen (API key shown as a read-only configured or not configured status with `.env` instructions)
- [ ] TEST-05 Test brief runs with and without new posts, a missed scheduled run, manual versus scheduled briefs, duplicate triggers, schedule and time-zone changes, OAuth failure cases, data deletion across both databases including partial failure, and retention cleanup

---

## Phase 6: Repurposing, evaluation and polish

Goal: a complete v1 with evidence that the agentic design helps.

- [ ] AGT-08 Build the Repurposing agent for all v1 formats
- [ ] API-06 Implement the repurpose endpoint
- [ ] UI-09 Build the Library screen with grouped drafts
- [ ] EVAL-01 Build the fixed-pipeline baseline in its own module
- [ ] EVAL-02 Create test case fixtures for all starting states, with labelled expected routes and written scoring rules for routing validity and routing quality
- [ ] EVAL-03 Build the comparison script and result storage, recording model, prompt, tool and fixture versions and confirming both variants use the same tools, data and settings
- [ ] EVAL-04 Review a sample of Critic scores and briefs by hand
- [ ] EVAL-05 Run the full comparison and record results in DECISIONS.md
- [ ] UI-10 Final pass for loading, empty and error states and responsive layout

---

## Phase 7: Hardening and release

- [ ] SEC-01 Complete the SECURITY.md checklist
- [ ] SEC-02 Review prompts and tools for prompt-injection exposure, including fetched pages that try to change database state
- [ ] TEST-06 Run the full TEST_PLAN.md
- [ ] DOC-03 Update README.md, ARCHITECTURE.md, DATABASE.md and API.md to match the final system
- [ ] DOC-04 Write the interview summary, listing only features that are built and tested
- [ ] REL-01 Tag the v1 release

---

## v2 backlog (planned, not dropped)

- [ ] V2-01 Brand-Deal Inbox: Gmail MCP server, email triage, reply drafts for approval
- [ ] V2-02 Creator Collab Matchmaker (Collab Scout): similar-creator matching and outreach drafts for approval
- [ ] V2-03 Review whether any publishing capability should be added, with its own approval design
- [ ] V2-04 Manage the YouTube API key through the UI (Option B in ADR-021): protected local endpoint, encrypted storage with the encryption key held outside the database, never returned, plus defined replace, delete and encryption-key rotation behavior, with tests
