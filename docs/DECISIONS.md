# DECISIONS: AI Personal Content Strategist

Permanent decisions and the reasons for them. Add a new entry whenever a design decision is made or changed. Do not delete old entries. Mark them superseded instead.
Status values: Accepted, Proposed, Superseded.

---

## ADR-001: Use LangGraph for orchestration
**Status:** Accepted
**Decision:** Build the agents as nodes in a LangGraph graph.
**Reason:** The project needs shared state, conditional routing, loops, pause and resume for approval, and checkpointing. LangGraph provides these directly.

## ADR-002: Supervisor-driven routing, not a fixed pipeline
**Status:** Accepted
**Decision:** Almost every node returns to the Supervisor, which chooses the next step from the current state. Only safety edges are fixed.
**Reason:** The project must be genuinely agentic. The route should change with the situation.

## ADR-003: Code computes eligible nodes, the model chooses among them
**Status:** Accepted
**Decision:** Routing is split. Code works out which nodes are allowed. The model chooses among them with a JSON schema output. Code validates the choice and falls back to a default if it is invalid.
**Reason:** A 4B model routes more reliably when the choices are few. Rules that must hold stay in code.

## ADR-004: Qwen3.5 4B through Ollama
**Status:** Accepted
**Decision:** Use `qwen3.5:4b` as the language model. Thinking mode is off for routing and classification.
**Reason:** Chosen by the project owner. It runs locally and supports tool calling. The risk is lower reliability than larger models, so an early test is required (MODEL-01). If it fails, try a larger model in the same family.

## ADR-005: Nomic embedding model for comment clustering
**Status:** Accepted
**Decision:** Use the nomic embedding model locally to group comments by theme.
**Reason:** Clustering with embeddings uses no LLM tokens, so thousands of comments can be handled cheaply. Only theme summaries reach the language model.

## ADR-006: SQLite through SQLAlchemy
**Status:** Accepted
**Decision:** Use SQLite for application data, with SQLAlchemy and Alembic.
**Reason:** Single-user, local-first project. SQLAlchemy keeps the schema portable if PostgreSQL is needed later.

## ADR-007: Separate database file for checkpoints
**Status:** Accepted (project owner, 2026-10-24)
**Decision:** Store LangGraph checkpoints in `checkpoints.db`, separate from application data.
**Reason:** Application migrations then never touch checkpoints.

## ADR-008: No publishing in v1
**Status:** Accepted
**Decision:** The system stops at approved drafts. The creator copies and posts manually, then marks the draft as posted.
**Reason:** Decided by the project owner. It removes a large risk area (write access, platform review, accidental posts) and keeps the focus on planning, writing and learning.

## ADR-009: Read-only platform access
**Status:** Accepted
**Decision:** Public data uses an API key. Owner-only metrics use read-only OAuth. No write scopes.
**Reason:** There is no publishing, so no write access is needed.

## ADR-010: Mark as posted links approved drafts to performance
**Status:** Accepted (project owner, 2026-10-24)
**Decision:** The creator marks an approved draft as posted and adds the link or ID. The Analyst only studies content marked this way.
**Reason:** Without publishing, the system cannot otherwise know which drafts were used.

## ADR-011: Human approval via LangGraph interrupt
**Status:** Accepted
**Decision:** Use interrupt with a checkpointer. Approvals exist for plans, drafts, Weekly Brief plans and depth increases.
**Reason:** Runs must pause for the creator and resume later, even after a restart.

## ADR-012: Weekly Brief runs automatically on Monday morning
**Status:** Superseded by ADR-022
**Decision:** APScheduler inside the FastAPI backend triggers the brief every Monday morning, with a startup catch-up check and one brief per week.
**Reason:** Decided by the project owner. APScheduler needs no extra services. The catch-up covers a computer that was off.

## ADR-013: Background worker inside the backend
**Status:** Accepted (project owner, 2026-10-24)
**Decision:** Runs execute in a background worker in the backend process. The UI polls for status.
**Reason:** Single user, so a queue and separate worker service are unnecessary in v1.

## ADR-014: MCP decision rule
**Status:** Accepted
**Decision:** If a server passes all checks, integrate it. If only some tools work, use it for those and build the rest as custom tools. If there are security, maintenance or reliability concerns, reject it and build a custom tool using the official API.
**Reason:** Decided by the project owner. It keeps the project working even when servers are weak or missing.

## ADR-015: Depth levels and token limits
**Status:** Accepted (project owner, 2026-10-24)
**Condition:** the depth levels and token limits are starting values and must be reviewed after MODEL-01, not treated as permanent settings.
**Decision:** Three depth levels (Quick, Standard, Deep) with fixed limits. Standard is the default. Each LLM call stays under about 6,000 input tokens. Numbers are starting values to be tuned after measuring.
**Reason:** A small local model has a small context window, and runs must stay predictable.

## ADR-016: Privacy for comments
**Status:** Accepted
**Decision:** Store comment text, likes, reply counts and dates only. Never usernames or reply text (clarified by ADR-028).
**Reason:** Usernames are not needed for theme analysis, and storing less reduces privacy risk.

## ADR-017: Evaluation compares a fixed pipeline with the Supervisor graph
**Status:** Accepted
**Decision:** Build a fixed-pipeline baseline in its own module and compare it with the Supervisor graph on the same test cases.
**Reason:** Decided by the project owner. It gives evidence that dynamic routing helps.

## ADR-018: Multi-platform text drafts in v1
**Status:** Accepted
**Decision:** v1 is not limited to YouTube. Repurposing produces text drafts for YouTube, Instagram, LinkedIn and X. Instagram data access is optional and read-only.
**Reason:** Decided by the project owner. Drafting needs no platform access, and optional reading keeps the feature working without a Business account.

## ADR-019: Frontend stack
**Status:** Accepted (project owner, 2026-10-24)
**Decision:** React with TypeScript, Vite, Tailwind CSS, TanStack Query and React Router.
**Reason:** React was chosen by the project owner. The rest are common defaults and can change before Phase 0 ends.

## ADR-020: Version 2 scope
**Status:** Accepted
**Decision:** Brand-Deal Inbox and Creator Collab Matchmaker (Collab Scout) are v2. They are listed in PRD.md and TASKS.md so they are not dropped.
**Reason:** They need extra access (email, creator discovery) and are not needed to prove the core agentic design.

## ADR-021: YouTube API key is environment-only in v1
**Status:** Accepted
**Decision:** The public-data API key is stored in `.env` and read through backend configuration. No API endpoint accepts, stores, replaces, deletes or returns it, and it is not stored in the database. The UI shows only whether it is configured and explains that changing it means editing `.env` and restarting the backend. In v2 the key becomes manageable through the UI (V2-04): a protected local endpoint, encrypted storage with the encryption key held outside the database, never returned, with defined replace, delete and key-rotation behavior.
**Reason:** Simplest option consistent with the local-first design. It removes a credential-handling endpoint and its attack surface from v1. OAuth refresh tokens still need database storage because they are obtained at runtime, so they stay encrypted with Fernet (ADR-009).

## ADR-022: Configurable Weekly Brief schedule, with manual briefs kept separate
**Status:** Accepted
**Decision:** The brief runs once per week at the creator's configured day, time and time zone. The default is Monday 08:00 `Asia/Kolkata`. Saved settings are the source of truth. Environment values are first-run defaults only. Scheduled briefs are limited to one per ISO week by a partial unique index on `period_key` where `trigger = scheduled`. Manual briefs have no period, never block the scheduled one and do not count toward it. Catch-up generates only the latest overdue scheduled brief. A trigger that fires while a brief is running is skipped and logged. Changing settings replaces the scheduler job immediately.
**Reason:** Closes the conflict between a fixed Monday schedule and the configurable settings in the API, and makes duplicate prevention precise. Replaces ADR-012.

## ADR-023: Versioned plans and drafts, with approvals tied to exact versions
**Status:** Accepted
**Decision:** Every plan and draft version is its own row with a lineage ID and version number. Saved versions are immutable. An approval references one exact version. Editing approved content creates a new version in `PENDING_APPROVAL`, supersedes the old one and creates a new approval request. `EDITED` during a pending approval means approve with edits: deterministic checks run, then the new creator-authored version is approved in the same transaction. Creator edits are not re-reviewed by the Critic. A decision for a superseded or cancelled item is rejected with 409. Mark as posted records the exact approved version. A weekly brief has no approval of its own: its linked plan is approved. `parent_draft_id` is reserved for repurposing and is not used for edit history.
**Reason:** The creator must always know exactly which text was approved and posted. The creator wrote their own edit, so a model review adds little, while the deterministic checks still protect length and format.

## ADR-024: Creator data deletion covers every storage location
**Status:** Accepted
**Decision:** `DELETE /creator/data` with a typed confirmation starts an idempotent background job with ordered steps: stop active runs and refuse new work, delete local OAuth tokens (provider revocation is best-effort and its failure never blocks local deletion), remove scheduler jobs, delete checkpoints by `thread_id`, delete application rows, delete cache entries, compact both databases. Each step is reported. Application rows are deleted after checkpoints, because the `thread_id` values are needed to find them. A failure gives `PARTIAL`, keeps the later steps' data, and the job can be retried. Evaluation results and the job record remain, because they contain no creator content. `.env` is not touched.
**Reason:** Deleting only application rows would leave checkpoints, cache and scheduler data behind and make the security promise false.

## ADR-025: Platform scope in v1
**Status:** Accepted
**Decision:** Drafting is supported for YouTube, Instagram, LinkedIn and X. Public research and owner analytics are planned for YouTube. Instagram analytics are optional and read-only. LinkedIn and X have no data integration in v1. The matrix is in PRD.md section 5.1 and is confirmed by the MCP checks.
**Reason:** Drafting needs no platform access. Data integrations are costly and not needed to prove the agentic design.

## ADR-026: Interrupted runs are recovered by the creator, not automatically
**Status:** Accepted
**Decision:** At startup, runs in `RUNNING` become `INTERRUPTED` and a `recovery` event is recorded. `WAITING_APPROVAL` runs are untouched. The creator resumes an interrupted run from its checkpoint or cancels it. Tool writes are idempotent and each node saves its result and step marker in one transaction. Cancellation is cooperative. Ollama becoming unavailable also interrupts the run.
**Reason:** Automatic resumption could start long model work unprompted. Idempotent writes make a manual resume safe.

## ADR-027: Local API and OAuth protections
**Status:** Accepted
**Decision:** The backend binds to `127.0.0.1`. CORS allows one configured origin. `POST`, `PUT` and `DELETE` need a matching `Origin` header and JSON content type. The `Host` header must be localhost. OAuth start is a POST, uses a single-use hashed `state` with a 10-minute lifetime, checks granted scopes, never puts tokens in redirects and handles denial and refresh failure. The callback is `/api/v1/auth/youtube/callback` and `GOOGLE_OAUTH_REDIRECT_URI` must match it. Fetch tools use a URL guard against private and metadata addresses.
**Reason:** A malicious web page can send requests to a local server through the browser. Loopback binding alone does not stop this.

## ADR-028: Small data decisions
**Status:** Accepted
**Decision:** (1) `replies` means the number of replies, stored as `reply_count`. Reply text is not stored. (2) Marking a draft as posted without a URL or ID is allowed and gives `posted_ref = none`. The Analyst reports that automated metrics are unavailable until the draft is linked, and matching uses URL or platform ID, never the title. (3) The 90-day comment retention and the cleanup schedule (startup and daily) are confirmed, with the details in DATABASE.md section 10. (4) Routing logs record the invalid-output category, retry result and fallback use, and a run that used a fallback is marked `degraded`.
**Reason:** Collect only the data analysis needs, keep the posting flow flexible, and avoid presenting a fallback-driven run as fully successful.

## ADR-029: Plan item identity across plan versions
**Status:** Accepted
**Decision:** Each plan version has its own `plan_items` rows. A stable `item_key` identifies the logical item across versions, unique per plan version. Carried-over items keep their `item_key` and copy their status. Drafts reference the exact item row they were written for and also store the `item_key`, so a logical item's drafts can be found across versions. Earlier versions' item rows are never changed.
**Reason:** A single `plan_id` foreign key cannot place one row in two plan versions. Separate rows keep plan history intact, and `item_key` keeps drafts linked when a plan is edited. Refines ADR-023.

## ADR-030: Creator profile is declared-only in v1; observed-style analysis deferred
**Status:** Accepted (project owner, 2026-10-24)
**Decision:** The Writer and Critic receive one creator-profile object built in code from settings: niche, tone preset, tone instructions and `profile_source = "declared"`. v1 contains declared preferences only. Audience level, topics already covered and comment insights are separate Listener outputs and research context, not part of this object. Analysis of the creator's existing content (titles, transcripts, comments) to infer observed style is deferred to a later phase (STYLE-01). When added, observed fields stay separate from declared ones, never overwrite them and are shown as notes with confidence and sample size, with no new approval type. It may start only after MODEL-01 and MCP-04 (own-video transcript scopes included) are complete and a stored-profile decision covers its table or `strategy_entries` use, retention and deletion (ADR-024). Onboarding does not include platform selection, because drafting for all four platforms needs no setup (ADR-025) and a platform setting would need new schema and API changes that have not been approved.
**Reason:** Transcript access for the creator's own videos may need a scope that conflicts with the read-only rule (ADR-009), and style analysis by a 4B model is untested. A single profile object lets observed fields be added later without changing the agents.

## ADR-031: Onboarding data model and endpoints
**Status:** Accepted (project owner, 2026-10-24)
**Condition:** channel-handle resolution (`POST /channel/resolve`) is revisited after MCP-01.
**Decision:** (1) Niche, `tone_preset`, `tone_instructions` and `onboarding_completed` live in `settings`. Niche and tone are removed from `creators`, which keeps the channel fields (ID, handle, title, verified). (2) Limits are 200 characters for niche and 500 for tone instructions, enforced by the API. (3) Each onboarding step saves through a partial `PUT /settings`. Skipping the optional channel step is saved on the server by `POST /onboarding/skip-channel` (`onboarding_channel_skipped`), so a reopened app resumes at Review. `onboarding_completed` is set only by `POST /onboarding/complete`, which calls the scheduler service to create the job. The scheduler service is built in Phase 1 (SCHED-00), so the contract does not depend on Phase 5. The `creators` row is created at the first onboarding save, so runs work without a channel. (4) Channel endpoints: `POST /channel/resolve`, `GET /creator/channels`, `PUT /creator/channel`, `DELETE /creator/channel`. Identifiers are parsed locally and never fetched. A channel is verified only by the server, through the API key or the connected account's channel list. (5) `POST /auth/youtube/start` takes `return_to` from a fixed list (`settings`, `onboarding`), stored with the `state`. (6) Until onboarding is completed, runs and manual briefs return 409 `ONBOARDING_REQUIRED` and no brief is scheduled. (7) Onboarding appears again after creator data deletion.
**Reason:** DATABASE.md and API.md both listed niche and tone, in `creators` and in `settings`, which would let the two drift apart. One source removes that. The `return_to` list lets the OAuth redirect come back to the onboarding screen without accepting a caller-supplied URL. Channel-change behavior is decided separately in ADR-032.

## ADR-032: Changing the YouTube channel keeps stored content, labelled by channel
**Status:** Accepted (project owner, 2026-10-24)
**Decision:** Changing or removing the saved channel (`PUT` or `DELETE /creator/channel`) never deletes stored videos, comments or insights. Content stays associated with its original channel through `content_items.channel_external_id`. Insights are traced to their channel through a new `comment_insight_sources` table (insight to content item). Code that reads the creator's own content or insights uses only those whose sources are own content of the currently saved channel, so a previous channel's data is not mixed into new plans or analysis. With no saved channel, no insight qualifies. Only creator data deletion (ADR-024) and the retention rules remove it. A future "remove data for a previous channel" action would need its own approval design.
**Reason:** Silent deletion on a channel change risks accidental data loss, and keeping history is cheap because the channel is already stored per item. The insight-to-source link is needed because `comment_insights` had only a creator and a run, which cannot tell which channel an insight came from.

## ADR-033: Comment retention clears text and links examples by reference
**Status:** Accepted (project owner, 2026-10-24)
**Decision:** After 90 days the cleanup job clears `comments.text` (nullable) and keeps the row, counts, dates and `processed_at`, so a comment is not processed twice. `comment_insights` no longer stores example text. Examples are rows in `comment_insight_examples` that reference comments, and they show as unavailable once the text is cleared. Themes, counts and coverage remain. This refines the 90-day retention in ADR-028 (3).
**Reason:** Deleting the whole row removed the `processed_at` marker, and copied example text in `examples_json` would have outlived the 90-day limit.

---

## Results log

Record spike and evaluation results here as they are produced.

- Review decisions accepted by the project owner: plan item identity (ADR-029), OAuth callback rules (ADR-027), full deletion sequence (ADR-024).
- DOC-08, 2026-10-24: the project owner accepted ADR-007, ADR-010, ADR-013, ADR-015, ADR-019, ADR-030, ADR-031, ADR-032 and ADR-033. ADR-015 is accepted on the condition that its limits are reviewed after MODEL-01. ADR-031 is accepted on the condition that channel-handle resolution is revisited after MCP-01. For ADR-033 the owner approved all three parts: text cleared after 90 days with the row kept, counts, dates and `processed_at` kept with no author information, and examples stored as references.
- MODEL-01 (qwen3.5:4b routing, tool selection, no-tool precision, structured output): not yet run
- MCP-01 to MCP-04 (server checks and decisions): not yet run
- Clustering method and thresholds: not yet chosen
- Evaluation test case count: not yet chosen
- Evaluation comparison results: not yet run
