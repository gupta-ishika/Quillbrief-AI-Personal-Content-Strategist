# MEMORY: Current Project State

Update this file after every task. DECISIONS.md holds permanent decisions. This file holds where the project is now.

---

## Current status

Phase 1 is 100% complete across both Backend and Frontend.
Phase 2 (Writer and Critic loop) is 100% complete across both Backend and Frontend.
Phase 3 (Goal decomposition and replanning) is in active development:
- GRAPH-06 (Goal decomposition and replanning): Supervisor dynamically decomposes goals into goal-specific task lists (e.g. script drafting vs. repurposing vs. analytics vs. audience research - AT-08), executes automatic task progression (marking executing node's task DONE), dynamically replans on rejection, respects immutable DONE tasks, normalizes continuous 1..N positions, and synchronizes to SQLite `tasks` table.
- GRAPH-07 (Skip and repeat logic): Supervisor skips Listener when comment insights are fresh and repeats Research when research is stale or data is thin (AT-05, AT-06); Analyst is skipped in weekly brief when there are no new posts (AT-07); tasks reflect SKIPPED and injected REPEAT actions dynamically.
- GRAPH-08 (Depth levels and limits enforcement): Strict enforcement of all limits across Quick, Standard, and Deep depth levels (supervisor steps 15/30/50, tool steps per agent 4/6/10, review limits 2/3/3, tool call caps for comments, videos, searches, and pages, and per-call token input caps with heuristic trimming). Budget stops record limit_reached event and report unfinished tasks.
- GRAPH-09 (Depth increase proposal and approval): Depth increase proposal approval flow (IT-05, IT-06, AT-05). When step budget is reached or data is thin, supervisor creates or routes to pending depth_increase approval; approval raises depth level for that run only (quick -> standard, standard -> deep), resumes run, and records run event note; rejection preserves depth limits.
- UI-06 (Runs history and routing log timeline): Implemented RunsScreen matching DESIGN Section 4.8 with run history list (status, depth, tokens, timestamps, degraded notice), detail view with task list (1..N sequence) and interactive routing log timeline (from/to node, decided by model vs. code, eligible nodes, token metrics, fallback indicators, reasons), and active run Cancel and Interrupted run Resume actions.

## Current task

Phase 3: Goal decomposition and replanning (TEST-03: Test thin data, stale data, limit reached and depth increase)

## Key decisions in force

- LangGraph multi-agent system with a Supervisor and ReAct loops
- Model: `qwen3.5:4b` through Ollama. Embeddings: nomic embedding model
- Database: SQLite through SQLAlchemy. Scheduler: APScheduler
- No publishing. The system stops at approved drafts, and the creator posts manually and marks them as posted
- Read-only platform access
- Weekly Brief on a configurable schedule (default Monday 08:00 Asia/Kolkata), shown in the React UI. Manual briefs are separate from the scheduled one (ADR-022)
- YouTube API key is environment-only in v1 (ADR-021)
- Plans and drafts are immutable versions. Approvals reference one exact version. Creator edits skip the Critic (ADR-023)
- Creator data deletion covers tokens, scheduler jobs, checkpoints, cache and application rows (ADR-024)
- Interrupted runs are recovered by the creator, not automatically (ADR-026)
- Local API protections and the OAuth contract are specified (ADR-027)
- Plan items have a stable `item_key` across plan versions (ADR-029)
- Accepted by the project owner on 2026-10-24 (DOC-08): separate checkpoint database (ADR-007), mark as posted (ADR-010), in-process background worker (ADR-013), depth levels and limits (ADR-015, confirmed after MODEL-01), frontend stack (ADR-019), declared-only creator profile (ADR-030), onboarding data model and endpoints (ADR-031, with handle resolution confirmed by MCP-01), channel change keeps content (ADR-032), comment retention clears text and links examples (ADR-033)
- Project owner accepted the plan-item identity, OAuth callback and deletion-sequence fixes
- Evaluation: fixed pipeline compared with the Supervisor graph

## Known issues and open points

- Transcript limitations confirmed: Other creators' transcripts are unavailable via official YouTube API; own-video transcripts require write scope `youtube.force-ssl`, which is prohibited by ADR-009. Video metadata, descriptions, and comments are used instead.
- Channel-handle resolution confirmed viable via YouTube Data API `forHandle` parameter (ADR-031).
- Clustering method and thresholds are not chosen.
- Number of evaluation test cases is not chosen.
- Specification documents are locked (v1.1).
- Onboarding (FR-0, DESIGN 4.0) is written into the documents, with matching DATABASE, API, SECURITY, TEST_PLAN and TASKS changes, and its decisions are accepted. DOC-06 is done.
- Channel change keeps stored content (ADR-032).
- Observed-style analysis of the creator's content is deferred (STYLE-01, ADR-030).
- Platform capabilities: full public research and owner analytics for YouTube, Instagram as text drafting target only in v1.

## Next steps

1. Run the consistency check (DOC-07), then lock the documents (DOC-02).
2. Set up the repository and skeletons (SET-01 to SET-05).
3. Run the model test and the MCP checks.
4. Start Phase 1: the thin agentic core.

---

## Update log

- GRAPH-06 done (2026-11-06): Implemented task list creation and dynamic replanning in Supervisor:
  - Goal decomposition (`decompose_goal_to_tasks`): Analyzes `user_goal` to generate goal-tailored task lists across 5 distinct categories (script drafting, content repurposing, performance analytics, research discovery, comprehensive planning), satisfying AT-08 ("two different goals produce different task lists").
  - Dynamic replanning (`apply_task_updates`): Supports adding, updating, removing, and reordering tasks; automatically transitions executing agent's task to DONE; dynamically injects revision task on rejected plan; guarantees that a resumed run never repeats or deletes a DONE task; normalizes sequential positions 1..N.
  - SQLite persistence (`sync_run_tasks`): Synchronizes state task list with database `tasks` table, mapping generated UUIDs.
  - Verified with 11 supervisor unit tests, 200 total backend tests, 0 Ruff errors, and 0 Mypy type discrepancies.
- UI-04, UI-05, TEST-02 done (2026-11-06): Completed frontend Draft Review screen, Critic evaluation panel, Drafts Library, and end-to-end integration test suite:
  - Draft Review screen (`DraftReview.tsx`): Displays formatted draft content, live word and character counters, platform limit status (YouTube Title, Description, Community Post, Instagram Caption, LinkedIn Post, X Thread), section indicators (Hook, Body, CTA), and immutable version switcher with approval warning notice.
  - Critic panel: 5-dimension rubric breakdown (Hook, Tone, Accuracy, Length, Relevance) with scores and visual bars, review iteration tracker ("Review X of 3"), review limit exhausted alert banner with open issues notice, and itemized strengths, suggestions, and issues.
  - Interactive actions: Approve draft, Reject with required feedback modal, inline edit mode with deterministic quality check validations, warning on editing approved content ("Saving creates a new version that needs approval"), one-click clipboard copy with visual feedback, mark as posted modal (with optional URL and platform ID), unlinked posted draft indicator ("Posted (no link)") with warning note and "Add link" dialog.
  - Drafts Library (`DraftsLibrary.tsx`): Multi-tab library view (Ready to post, Posted, All drafts) with platform and kind filters, direct review navigation, and quick copy/mark-as-posted actions.
  - Test suite (`DraftReview.test.tsx`): 9 tests covering rendering, rubric display, review limit exhausted banner, approval, rejection with feedback, inline edit validation, editing before/after approval, copy to clipboard, and mark as posted flows. Zero TypeScript or ESLint errors, clean production bundle.
- GRAPH-05, DB-03, VER-02, API-03 done (2026-11-06): Completed backend engine, database, and API layer for Writer-Critic loop and draft versioning:
  - Graph routing (`backend/app/graph/builder.py`): writer and critic nodes integrated with cyclic revision edge, review-count limit check, best-draft fallback, and interrupt-based human approval step.
  - Draft & Critic evaluation models (`backend/app/db/models.py`, `backend/alembic/versions/`): draft lineage tracking, immutable versions, check constraints, cascade deletions.
  - Draft REST API (`backend/app/api/v1/drafts.py`): `GET /drafts`, `GET /drafts/{id}`, `GET /drafts/{id}/versions`, `POST /drafts/{id}/edit` with 422 CHECKS_FAILED & 409 STALE_VERSION, `POST /drafts/{id}/mark-posted` with 409 NOT_APPROVED & 409 STALE_VERSION, and `POST /drafts/{id}/link-posted` with 409 NOT_POSTED & 422 LINK_REQUIRED.
  - Comprehensive unit and integration test suites passing (31 test files, 100% pass rate).
- AGT-04, TOOL-05, AGT-05 done (2026-11-03): Implemented the Writer agent, deterministic Draft Checker, and Critic agent for Phase 2:
  - Writer agent (`app/agents/writer.py`) producing structured drafts for scripts, titles, descriptions, captions, and posts adhering to 4,000 token limit, declared-only creator profile, untrusted data boundary directives, and immutable draft versioning.
  - Draft checker (`app/tools/draft_checker.py`) enforcing word count, character count, format-required sections (Hook, Body, CTA), and platform length limits for YouTube, Instagram, LinkedIn, and X with zero LLM token consumption.
  - Critic agent (`app/agents/critic.py`) scoring drafts against 5 rubric dimensions (Hook, Tone, Accuracy, Length, Relevance), enforcing deterministic check failures as hard blockers for passing, depth-dependent review limits (Quick: 2, Standard: 3, Deep: 3), best-draft selection across lineage on review exhaustion, and persistence in `critic_evaluations` table.
  - Full test suite verified with all 14 tests passing in `test_draft_checker.py`, `test_writer_agent.py`, and `test_critic_agent.py`, 0 Ruff errors, and 0 Mypy errors across 67 source files.
- UI-01, UI-02, UI-03, ONB-02 done (2026-10-27): Implemented the full Phase 1 React frontend in accordance with DESIGN 4.0:
  - Responsive app shell (`AppLayout`, `Sidebar`) with pending approvals badge, system health indicator, tablet icon collapsing, and mobile bottom navigation.
  - Typed REST API client in `src/api/client.ts` with error handling for API error formats, origin and host headers, and endpoints for onboarding, runs, approvals, plans, and settings.
  - First-run onboarding wizard (`OnboardingWizard`) replacing the app shell prior to completion: Step 1 Niche with 200-char live validation; Step 2 Tone with 5 preset cards and 500-char optional instructions; Step 3 YouTube channel by handle/ID/URL with local format validation, resolution checks, read-only OAuth initiation, and persistent skip (`POST /onboarding/skip-channel`); Step 4 Review summary with verified/unverified/none badges, read-only API key status, default schedule with Asia/Kolkata timezone, and completion (`POST /onboarding/complete`). Supports seamless resume at review step after skip.
  - Home screen (`HomeScreen`) with goal text area, 3-level depth selector cards (`quick`, `standard`, `deep`), run launching, active run progress tracking with status badges, step count, token counter, cooperative cancellation modal, restart recovery resumption, and degraded-run alert banner.
  - Approvals inbox (`ApprovalsInbox`) with oldest-first sorting, item type badges, time waiting, and empty state.
  - Plan review screen (`PlanReview`) displaying plan item cards with topic, format, platform, objective, rationale, expandable source evidence, inline editing mode creating new version with approval requirement notification, and reject modal requiring feedback text.
  - Settings screen (`SettingsScreen`) for editing profile and schedule preferences.
  - Comprehensive unit and integration test suites passing in Vitest (8/8 tests), zero ESLint errors, and clean production build.
- TOOL-07 done (2026-10-25): Built URL guard for web fetch tools with SSRF protection, loopback/private/metadata IP blocking, redirect validation, streaming response size caps, and timeouts (UT-28, RULES.md).
- TOOL-04 done (2026-10-25): Built MCP adapter with strict per-agent tool allowlists, refusal and logging of unauthorized tool calls, and provenance tracking (UT-32).
- TOOL-03 done (2026-10-25): Built state and database tools for content items, comments, insights, plans, and drafts with provenance tracking, ADR-032 channel filtering, and LangChain ReAct tool wrappers (UT-32).
- TOOL-02 done (2026-10-25): Built comment clusterer with local Ollama embeddings (nomic-embed-text) and scikit-learn, with deterministic output, exact count conservation, 2-3 examples per theme, and zero LLM token consumption (UT-10, ADR-005, ADR-033).
- TOOL-01 done (2026-10-25): Built comment fetcher tool with author anonymity (ADR-016), spam and emoji-only filtering, deduplication, engagement-recency ranking, depth level capping, and coverage tracking (UT-09).
- SCHED-00 done (2026-10-25): Built APScheduler scheduler service with SQLAlchemy job store, Weekly Brief job management (gated by onboarding_completed, replaceable on settings update), placeholder target for AGT-07, and lifespan lifecycle in FastAPI.
- GRAPH-04 done (2026-10-24): Implemented dedicated SQLite checkpointer (sync and async with WAL & busy timeout) and thread checkpoint deletion service for creator data isolation (ADR-007, ADR-024).
- TEST-01, TEST-07, TEST-08 done (2026-10-27): Implemented automated test suites in test_routes_integration.py, test_failure_paths.py, and test_permission_and_injection.py covering new vs established creator routing (AT-01, AT-02), rejected plan revision (AT-03, IT-02), supervisor fallback and degraded run indicator (UT-31), structured tool errors, secret isolation and MCP permission boundaries (UT-33, RT-09), prompt injection defense (RT-10), and channel change insight filtering (UT-39).
- ONB-01 and PROF-01 done (2026-10-26): Implemented onboarding backend endpoints (GET /onboarding, POST /onboarding/skip-channel, POST /onboarding/complete, POST /channel/resolve, GET /creator/channels, PUT /creator/channel, DELETE /creator/channel), partial PUT /settings with server-side validation (UT-34), local YouTube handle and channel ID resolution (UT-35), creator profile builder from declared settings fields (UT-38, ADR-030), and channel preservation (ADR-032).
- AGT-03 done (2026-10-25): Built Strategist agent in app/agents/strategist.py producing structured content plan items with 3 balanced source labels ('comment', 'similar_creator', 'own_idea'), 6,000 token input cap, rejection feedback revision with immutable versioning, database persistence, and deterministic fallback.
- AGT-02 done (2026-10-25): Built ReAct Research agent in app/agents/research.py with depth-budget enforcement (Quick 4, Standard 6, Deep 10 tool steps), 6,000 token input cap, untrusted data boundary directives, registered research tools in app/tools/research_tools.py (web_search, web_fetch with SSRF defense, youtube_video_search, youtube_channel_lookup), and deterministic fallback.
- AGT-01 done (2026-10-25): Built ReAct Listener agent in app/agents/listener.py with depth-budget enforcement (Quick 4, Standard 6, Deep 10 tool steps), 4,000 token input cap, untrusted data boundary directives, 7 registered listener tools in app/tools/listener_tools.py, deterministic synthesis fallback, and database persistence.
- TOOL-07 done (2026-10-25): Built URL guard in app/tools/url_guard.py with strict scheme checking, SSRF protection against private/loopback/link-local/metadata addresses, redirect validation, and streaming size caps.
- TOOL-04 done (2026-10-25): Built MCP adapter in app/tools/mcp_adapter.py with per-agent allowlists and provenance tracking.
- TOOL-03 done (2026-10-25): Built state and database tools in app/tools/database_tools.py with provenance tracking and channel filtering.
- TOOL-02 done (2026-10-25): Built comment clusterer with local embeddings in app/tools/comment_clusterer.py.
- TOOL-01 done (2026-10-25): Built comment fetcher in app/tools/comment_fetcher.py with spam and emoji filtering and ranking.
- SCHED-00 done (2026-10-25): Implemented APScheduler service with SQLAlchemy job store.
- GRAPH-04 done (2026-10-25): Implemented dedicated SQLite checkpointer in checkpoints.db with thread checkpoint deletion service.
- SEC-03 done (2026-10-26): Enforced strict local API protections in security_headers_middleware with single origin CORS, missing/foreign Origin header rejection on state-changing requests, Host validation preventing DNS rebinding, and JSON-only body enforcement (UT-27).
- VER-01 done (2026-10-26): Implemented content plan versioning endpoints (GET /plans/{id}, POST /plans/{id}/edit) with lineage tracking, immutable versions, optimistic locking checks (STALE_VERSION), exact-version approval requests, and cancellation of superseded approvals.
- BG-01 and REC-01 done (2026-10-26): Implemented background worker for graph runs with step boundary cooperative cancellation and status updates (RUNNING, WAITING_APPROVAL, COMPLETED, STOPPED, FAILED), startup crash recovery (RUNNING -> INTERRUPTED with recovery event and preserved pending approvals), and full content graph assembly in builder.py.
- API-01 and API-02 done (2026-10-25): Implemented FastAPI REST endpoints for runs (start, list, get, routing-log, cancel, resume) and approvals (list, get, decision for APPROVED/REJECTED/EDITED) conforming to API.md v1.1 error conventions and local protections.
- HITL-01 and HITL-02 done (2026-10-25): Implemented human approval node with LangGraph interrupt, Approval table tracking, plan status transitions (APPROVED, REJECTED, and EDITED creator versioning via ADR-029), and process restart resumption across independent sessions using SQLite checkpointer.
- GRAPH-03 done (2026-10-25): Enforced depth level step budgets (Quick 6, Standard 12, Deep 20) and cycle repeat detection in Supervisor node with degraded run annotations.
- GRAPH-02 done (2026-10-24): Implemented Supervisor routing with code-calculated node eligibility, structured JSON decision output, and deterministic fallback.
- GRAPH-01 done (2026-10-24): Defined LangGraph agent state and Pydantic decision models with strict schema validation.
- DB-02 done (2026-10-24): Configured SQLite options (PRAGMA foreign_keys, WAL mode, busy_timeout 5000ms) and repository functions for creators, settings, runs, approvals, plans, drafts, comments, and metrics.
- DB-01 done (2026-10-24): Created SQLAlchemy models and initial Alembic migrations for core tables matching DATABASE.md v1.1.
- DATA-01 done (2026-10-24): Collected test fixture datasets for creator profile, videos, anonymous comments, metrics, and evaluation routes.
- MCP-01 to MCP-05 done (2026-10-24): Audited MCP servers, confirmed channel lookup and read-only invariants in DECISIONS.md.
- MODEL-01 done (2026-10-24): Benchmarked qwen3.5:4b on routing, schema adherence, and tool calling with think: False.
- DOC-01, DOC-07, DOC-02 done (2026-10-24): Completed full consistency audit across PRD, ARCHITECTURE, DATABASE, API, DESIGN, SECURITY, RULES, and TEST_PLAN; verified all 33 ADRs; locked PRD, ARCHITECTURE, DATABASE, and API specifications (v1.1).
- API-00 done (2026-10-24): Defined all Pydantic schemas in `backend/app/schemas/` matching API.md (common, runs, approvals, plans, drafts, briefs, insights, settings, onboarding, evaluation) and verified validation with tests, ruff, and mypy.
- SET-05 done (2026-10-24): Built database and Ollama health service in `backend/app/services/health.py`, connected to `/health` and `/api/v1/health`, added unit and integration tests with mocks and live Ollama, verified with pytest, ruff, and mypy.
- SET-04 done (2026-10-24): Verified Ollama installation, pulled `qwen3.5:4b`, confirmed `nomic-embed-text:latest` embedding model, recorded model confirmation in DECISIONS.md.
- SET-03 done (2026-10-24): Created frontend project with Vite, React, TypeScript, Tailwind CSS, TanStack Query, React Router, Lucide icons, Vitest, Testing Library, ESLint flat config; verified test, build, and lint.
- SET-02 done (2026-10-24): Created backend project structure (`backend/app`, `backend/tests`), `pyproject.toml`, FastAPI app with security middleware and health endpoint, installed dependencies in `.venv`, verified with ruff, mypy, and pytest.
- SET-01 done (2026-10-24): Initialized Git repository, created `.gitignore`, `.env.example`, `docs/RULES.md`, and organized documentation markdown files under `docs/`.
- Documents drafted. No implementation yet.
- DOC-08 done (2026-10-24): ADR-007, 010, 013, 015, 019, 030, 031, 032 and 033 accepted. ADR-015 on the condition of a post-MODEL-01 review, ADR-031 on the condition that handle resolution is revisited after MCP-01. DOC-06 and DOC-08 checked off in TASKS.md. DOC-07 and DOC-02 remain open. MODEL-01, MCP-01 to MCP-05 and SET-04 are not run.
- API-key storage decided: environment only in v1.
- Second review round applied: skip of the channel step is persisted (`onboarding_channel_skipped`), the creator row exists without a channel, insights are traced to channels through `comment_insight_sources`, comment retention clears text instead of deleting rows and examples are references (ADR-033), a basic scheduler (SCHED-00) is built in Phase 1, Host check tests include the port, and PRD validation matches the API. DOC-08 added for the Proposed ADRs. Spec-lock is still pending, and MODEL-01 and MCP-01 to MCP-05 are not run.
- Review fixes applied: PRD G5 default schedule, schedule saved without a job before onboarding completes, `GET /settings` for the review schedule, resume wording, Listener context versus declared profile, MCP-04 covers own-video transcripts, Host check includes the port, ADR-032 proposed.
- Documents updated to v1.1: versioning, scheduling, deletion, platform scope, recovery, OAuth and local-API protections. Tasks and tests added. DOC-02 stays unchecked.
- Project owner approved ADR-029, the ADR-027 callback rules and the ADR-024 deletion sequence. Embedding default set to `nomic-embed-text`, to be confirmed in SET-04.
- DOC-06 drafted into the documents: onboarding is niche, tone, optional channel and review, with no platform selection. Added ADR-030 (declared-only creator profile) and ADR-031 (onboarding data model and endpoints), both Proposed. Added ONB-01 to ONB-03, PROF-01, TEST-08 and STYLE-01. Phase 1 now lists UT-32, UT-33 and RT-09 in TEST-08. New tests UT-34 to UT-38, RT-10, E2E-16 and E2E-17.
