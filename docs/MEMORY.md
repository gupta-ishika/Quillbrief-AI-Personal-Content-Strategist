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

## Current task

SET-05: Add a health check that confirms the database, Ollama and both models

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
- Accepted by the project owner on 2026-10-24 (DOC-08): separate checkpoint database (ADR-007), mark as posted (ADR-010), in-process background worker (ADR-013), depth levels and limits (ADR-015, as starting values to review after MODEL-01), frontend stack (ADR-019), declared-only creator profile (ADR-030), onboarding data model and endpoints (ADR-031, with handle resolution revisited after MCP-01), channel change keeps content (ADR-032), comment retention clears text and links examples (ADR-033)
- Project owner accepted the plan-item identity, OAuth callback and deletion-sequence fixes
- Evaluation: fixed pipeline compared with the Supervisor graph

## Known issues and open points

- The model test (MODEL-01) has not been run. Routing and tool selection reliability with a 4B model is the biggest technical risk.
- MCP servers have not been checked (MCP-01 to MCP-04). Transcripts of other creators' videos are a known risk.
- Clustering method and thresholds are not chosen.
- Number of evaluation test cases is not chosen.
- ADR-015 limits must be reviewed after MODEL-01, and channel-handle resolution revisited after MCP-01.
- Documents are drafts under review and not yet locked. Version 1.1 applies the decisions above. A fresh consistency read is still needed (DOC-07).
- Onboarding (FR-0, DESIGN 4.0) is written into the documents, with matching DATABASE, API, SECURITY, TEST_PLAN and TASKS changes, and its decisions are accepted. DOC-06 is done.
- Channel change keeps stored content (ADR-032). Channel lookup by handle must be confirmed at MCP-01.
- Observed-style analysis of the creator's content is deferred (STYLE-01, ADR-030).
- Third review pass fixed: plan-item identity (`item_key`), OAuth callback rules, full deletion sequence, MCP provenance and permission tests, API-key status shape, embedding model default.
- Platform capabilities are decided in the documents but are confirmed only after the MCP checks.

## Next steps

1. Run the consistency check (DOC-07), then lock the documents (DOC-02).
2. Set up the repository and skeletons (SET-01 to SET-05).
3. Run the model test and the MCP checks.
4. Start Phase 1: the thin agentic core.

---

## Update log

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
