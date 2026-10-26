# MEMORY: Current Project State

Update this file after every task. DECISIONS.md holds permanent decisions. This file holds where the project is now.

---

## Current status

Planning is complete in draft form. No code has been written yet.

## Completed

- Project idea defined and scoped (v1 and v2)
- PRD.md written
- ARCHITECTURE.md written
- DATABASE.md, API.md, DESIGN.md and RULES.md written
- TASKS.md written
- TEST_PLAN.md, SECURITY.md and DECISIONS.md written
- README.md and `.env.example` written
- API-key decision applied (ADR-021)
- Versioning, scheduling, deletion, platform scope, recovery and local-API rules decided and written into the documents (ADR-022 to ADR-028)
- SET-01 completed: Git repo initialized, `.gitignore`, `.env.example`, `docs/RULES.md` created, spec docs moved to `docs/` folder
- SET-02 completed: Backend scaffolded (FastAPI, Ruff, mypy, pytest), virtualenv configured, dependencies installed, health endpoints and security middleware tested cleanly
- SET-03 completed: Frontend scaffolded (Vite, React, TypeScript, Tailwind CSS, TanStack Query, React Router, Lucide, Vitest, Testing Library, ESLint), verified tests, build, and lint cleanly
- SET-04 completed: Confirmed Ollama installation, pulled `qwen3.5:4b` and verified `nomic-embed-text:latest`, confirmed exact names and recorded in DECISIONS.md
- SET-05 completed: Implemented health service checking SQLite DB connection, Ollama reachability, model verification, degradation handling, and API key protection; verified via pytest, ruff, and mypy
- API-00 completed: Created full field-level Pydantic schemas matching API.md across common, runs, approvals, plans, drafts, briefs, insights, settings, onboarding, and evaluation contracts with comprehensive validation tests
- DOC-01, DOC-07, DOC-02 completed: Cross-document consistency verified against all 33 ADRs; PRD, ARCHITECTURE, DATABASE, and API specifications are locked (v1.1)
- MODEL-01 completed: Tested `qwen3.5:4b` using `think=False` on routing (100% accuracy), JSON schema adherence (100%), tool selection (100%), and no-tool precision (100%). Latency averaged 9.6s. ADR-015 limits reviewed and confirmed.
- MCP-01 to MCP-05 completed: Evaluated servers against Section 11 checklist. Confirmed YouTube `forHandle` parameter for ADR-031 handle resolution; split YouTube tools to custom wrappers for quota/token capping and credential isolation; web search passed with result capping; raw web fetch rejected for SSRF risk and routed through custom URL guard (TOOL-07); Instagram MCP deferred for v1; confirmed official transcript download is unavailable for other creators' videos and prohibited for own videos under read-only rule ADR-009 (`youtube.force-ssl` rejected). All pass/fail results logged in DECISIONS.md.
- DATA-01 completed: Created realistic fixture datasets (`creator.json`, `videos.json`, `comments.json`, `performance_metrics.json`, `evaluation_cases.json`) in `backend/tests/fixtures/` and verified with unit tests `backend/tests/test_fixtures.py` ensuring anonymity (UT-14) and coverage of all 5 ARCHITECTURE.md 6.4 evaluation routes.
- DB-01 completed: Created SQLAlchemy 2.0 models and Alembic migrations for all Phase 1 tables: `creators`, `settings`, `goals`, `runs` (including `INTERRUPTED` status and `degraded` indicators), `tasks`, `routing_logs`, `token_usage`, `run_events`, `content_items`, `comments` (with nullable `text` for 90-day retention), `comment_insights`, `comment_insight_sources`, `comment_insight_examples`, `research_findings`, `content_plans`, `plan_items`, `drafts`, `approvals`, and `cache_entries`. Verified with migration application and 22 unit tests.
- DB-02 completed: Configured SQLite pragmas (`foreign_keys = ON`, `journal_mode = WAL`, `busy_timeout = 5000`) on SQLite engine connections and authored repository modules in `backend/app/db/repositories/` covering `creator`, `settings`, `runs`, `content`, and `plans`. Verified with 26 unit tests covering channel isolation (ADR-032), versioning, and approvals.
- GRAPH-01 completed: Defined `ContentState` TypedDict and Pydantic decision models (`SupervisorDecision`, `CriticEvaluationDecision`, `DepthIncreaseDecision`, `TaskUpdate`) with strict constraints and extra field forbidding. Verified with 32 unit tests.
- GRAPH-02 completed: Built Supervisor node with deterministic code-calculated node eligibility (`calculate_eligible_nodes`), single-node direct routing without LLM calls (UT-03), structured model choice (`think=False`), bounded single-retry validation, deterministic code fallback (`get_deterministic_default_node`), run degradation marking, and routing log persistence. Verified with 37 unit tests.
- GRAPH-03 completed: Added depth level step budgets (`Quick`: 15, `Standard`: 30, `Deep`: 50 per ADR-015/Section 10) and repeat detection algorithms (consecutive 3-node, 2-node alternating cycle, 3-node cycle per UT-04 and UT-05) halting execution with `stop_reason` and writing audit logs to SQLite. Verified with 40 unit tests.

## Current task

GRAPH-04: Add the SQLite checkpointer in its own database file

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

- TOOL-07 done (2026-10-25): Built URL guard for web fetch tools with SSRF protection, loopback/private/metadata IP blocking, redirect validation, streaming response size caps, and timeouts (UT-28, RULES.md).
- TOOL-04 done (2026-10-25): Built MCP adapter with strict per-agent tool allowlists, refusal and logging of unauthorized tool calls, and provenance tracking (UT-32).
- TOOL-03 done (2026-10-25): Built state and database tools for content items, comments, insights, plans, and drafts with provenance tracking, ADR-032 channel filtering, and LangChain ReAct tool wrappers (UT-32).
- TOOL-02 done (2026-10-25): Built comment clusterer with local Ollama embeddings (nomic-embed-text) and scikit-learn, with deterministic output, exact count conservation, 2-3 examples per theme, and zero LLM token consumption (UT-10, ADR-005, ADR-033).
- TOOL-01 done (2026-10-25): Built comment fetcher tool with author anonymity (ADR-016), spam and emoji-only filtering, deduplication, engagement-recency ranking, depth level capping, and coverage tracking (UT-09).
- SCHED-00 done (2026-10-25): Built APScheduler scheduler service with SQLAlchemy job store, Weekly Brief job management (gated by onboarding_completed, replaceable on settings update), placeholder target for AGT-07, and lifespan lifecycle in FastAPI.
- GRAPH-04 done (2026-10-24): Implemented dedicated SQLite checkpointer (sync and async with WAL & busy timeout) and thread checkpoint deletion service for creator data isolation (ADR-007, ADR-024).
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
