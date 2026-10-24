# DATABASE: AI Personal Content Strategist

Status: Locked v1.1
Scope: application data model. Graph checkpoints are separate (see section 8).

---

## 1. General rules

- Database: SQLite through SQLAlchemy. Migrations use Alembic.
- Enable `PRAGMA foreign_keys = ON` and WAL mode on every connection.
- Primary keys are UUID strings stored as TEXT.
- Timestamps are UTC, stored as ISO 8601 text, in `created_at` and `updated_at` columns.
- Status columns are TEXT with a CHECK constraint listing the allowed values.
- Structured payloads that are never queried field by field use JSON columns, named `*_json`.
- Raw data (comments, transcripts, pages) lives here. Shared graph state holds only IDs and summaries.
- Writes come only from code-controlled tool functions, never directly from the model.
- Comments store text, like count, reply count and date only. Usernames and reply text are never stored.
- **Versions are rows.** A plan or draft version is its own row. Once a version leaves its editable state (see section 5), its content is never changed. An edit creates a new row.
- **Approvals are immutable.** A decided or cancelled approval row is never updated or deleted, except by creator data deletion (section 11).

---

## 2. Creator and access

### creators
- id, display_name, audience_level
- youtube_channel_id (nullable), youtube_channel_handle (nullable), youtube_channel_title (nullable), youtube_channel_verified (boolean, default false), instagram_account_id (nullable)
- created_at, updated_at

One row in v1, created the first time onboarding saves any value (niche, tone or channel), so goals and runs always have a `creator_id` even if the creator never connects a channel. Niche and tone are not stored here. They live in `settings`, which is their only source (ADR-031). A channel entered without a configured API key is stored as unverified, as an ID or a handle. The Listener resolves and verifies it on the first run that has a configured key. The table exists so multi-user support can be added later.

### oauth_tokens
- id, creator_id (FK), platform (`youtube`, `instagram`)
- scopes (text), refresh_token_encrypted
- state (`connected`, `needs_reauth`)
- created_at, updated_at

Unique on (creator_id, platform). Refresh tokens are encrypted with Fernet. Access tokens are held in memory only and refreshed on demand, so no access token or expiry is stored. Public data uses an API key from the environment (ADR-021) and has no row here.

### oauth_states
- state_hash (PK), platform, return_to (`settings` or `onboarding`), expires_at, used_at (nullable)

Short-lived (10 minutes), single-use values for the OAuth `state` parameter. Only a hash is stored. Expired rows are removed by the cleanup job.

### settings
- key (PK), value_json, updated_at

Keys include `default_depth_level`, `brief_day`, `brief_time`, `time_zone`, `niche` (1 to 200 characters), `tone_preset` (`professional`, `friendly`, `educational`, `conversational`, `humorous`), `tone_instructions` (0 to 500 characters) `onboarding_channel_skipped` (boolean, default false, set only by `POST /onboarding/skip-channel`) and `onboarding_completed` (boolean, default false, set only by the onboarding completion endpoint). Limits are enforced by the API, not only the UI. Environment values for the brief schedule are first-run defaults only: they are used when the setting row does not exist. Once a row exists, the saved setting wins.

### deletion_jobs
- id, status (`PENDING`, `RUNNING`, `COMPLETED`, `PARTIAL`, `FAILED`)
- steps_json (each step with its name, status and a short error code)
- requested_at, finished_at (nullable)

Deliberately has no foreign key to `creators` and holds no creator content, so it survives a deletion and can report its result.

---

## 3. Runs and routing

### goals
- id, creator_id (FK), text, created_at

### runs
- id, goal_id (FK, nullable for scheduled and manual brief runs), run_type (`goal`, `weekly_brief`, `post_mortem`)
- depth_level (`quick`, `standard`, `deep`)
- status: `PENDING`, `RUNNING`, `WAITING_APPROVAL`, `COMPLETED`, `FAILED`, `STOPPED`, `INTERRUPTED`
- thread_id (LangGraph thread), step_count, tokens_used, stop_reason (nullable)
- degraded (bool), degraded_reason (nullable)
- started_at, finished_at, created_at, updated_at

`INTERRUPTED` means the run was `RUNNING` when the backend stopped, or a dependency such as Ollama became unavailable. It is resumable (section 12.1 of ARCHITECTURE.md). `degraded` is true when a Supervisor decision fell back to the code default or a required tool failed, and the UI must say so.

### tasks
- id, run_id (FK), title, agent, position
- status: `TODO`, `DONE`, `SKIPPED`, `FAILED`
- created_at, updated_at

The Supervisor's task list. It can add, remove and reorder tasks, so `position` is rewritten on change. A resumed run never repeats a `DONE` task.

### routing_logs
- id, run_id (FK), step_number
- from_node, to_node, reason
- decided_by (`model`, `code`), eligible_nodes_json
- output_status (`valid`, `retried_valid`, `fallback`), invalid_category (nullable: `bad_json`, `schema_violation`, `ineligible_node`, `timeout`)
- tokens_in, tokens_out, created_at

One row per Supervisor decision. Index on (run_id, step_number).

### token_usage
- id, run_id (FK), node, tokens_in, tokens_out, created_at

### run_events
- id, run_id (FK), event_type (`tool_result`, `tool_error`, `limit_reached`, `model_fallback`, `recovery`, `note`), payload_json, created_at

Used for audit and debugging. Tool results are stored trimmed to the capped size. Payloads never contain secrets or full third-party content.

---

## 4. Content data

### content_items
- id, creator_id (FK), platform, external_id
- owner_type (`own`, `similar`), channel_external_id
- title, description, published_at, transcript_text (nullable), fetched_at

Unique on (platform, external_id). Holds the creator's own videos and similar creators' content found by Research.

### comments
- id, content_item_id (FK), external_id, text (nullable, cleared after 90 days, see section 10), like_count, reply_count (nullable), published_at
- cluster_label (nullable), processed_at (nullable)

Unique on (content_item_id, external_id). `processed_at` marks comments already analysed, so later runs only read new ones. When the text is cleared the row stays, so a comment is never read twice, but the text is not kept. `reply_count` is the number of replies to the comment, where the platform reports it. Reply text is not stored.

### comment_insights
- id, creator_id (FK), run_id (FK), theme_label, comment_count
- coverage_analyzed, coverage_total
- status (`current`, `superseded`), created_at

Insights hold no comment text. Example comments are referenced, not copied (ADR-033).

### comment_insight_sources
- insight_id (FK), content_item_id (FK)

Links each insight to the content items it was derived from, so every insight can be traced to its channel through `content_items.channel_external_id` (ADR-032). One insight can have several sources.

### comment_insight_examples
- insight_id (FK), comment_id (FK)

Two or three example comments per insight, by reference. The UI shows an example only while its comment text exists. After the text is cleared the example is shown as no longer available, and the theme, count and coverage remain.

**Channel rule.** Current plans and analysis use an insight only if all its sources are own content (`owner_type = own`) of the channel currently saved in `creators`. With no saved channel, no insight qualifies. Insights from a previous channel stay stored but are excluded.

### research_findings
- id, run_id (FK)
- kind: `opportunity`, `similar_creator`, `trend`, `gap`
- topic, reason, evidence_json (source links and notes), created_at

### cache_entries
- key (PK), value_json, expires_at

Caches search results, fetched pages and transcripts.

---

## 5. Plans, drafts and approvals

### content_plans
- id (this row is one plan version), lineage_id, version, previous_version_id (FK, nullable)
- run_id (FK), created_by (`strategist`, `creator`)
- status: `DRAFT`, `PENDING_APPROVAL`, `APPROVED`, `REJECTED`, `SUPERSEDED`
- feedback_text (nullable), created_at, approved_at (nullable)

Unique on (lineage_id, version). A rejected plan is revised into a new version by the Strategist. Editing a plan creates a new version and marks the earlier version `SUPERSEDED`. Only the latest version can be `PENDING_APPROVAL` or `APPROVED`.

### plan_items
- id (this row is one plan item in one plan version), plan_id (FK)
- item_key (stable identity of the logical item, the same in every version of the plan)
- topic, format, platform, objective, reason
- source_type (`comment`, `similar_creator`, `own_idea`), source_ref (nullable)
- priority, scheduled_day (nullable)
- status: `PLANNED`, `DRAFTING`, `DONE`, `DROPPED`

Unique on (plan_id, item_key). When a plan is edited, every item of the new version is a new row in the new `plan_id`. Items that carry over keep their `item_key`, and their `status` is copied. Changed items keep their `item_key` too, with new content. New items get a new `item_key`. Earlier versions keep their own item rows unchanged, so the history of each plan version is preserved. A dropped item has no row in the new version, and its drafts stay in the Library.

### drafts
- id (this row is one draft version), lineage_id (the same for every version of one logical draft; equal to the `id` of version 1)
- version (1, 2, 3, ...), previous_version_id (FK, nullable)
- plan_item_id (FK, nullable): the exact plan item row the draft was written for, so history stays accurate
- item_key (nullable): the logical plan item. Drafts of an item across plan versions are found through `item_key`
- parent_draft_id (FK, nullable): set **only** for repurposed drafts, and points to the approved source version. It does not describe edit history.
- kind: `script`, `title`, `description`, `community_post`, `caption`, `linkedin_post`, `x_thread`
- platform, content, created_by (`model`, `creator`)
- status: `WRITING`, `IN_REVIEW`, `PENDING_APPROVAL`, `APPROVED`, `REJECTED`, `SUPERSEDED`, `POSTED`
- posted_at (nullable), posted_ref (nullable: `url`, `platform_id`, `none`), posted_url (nullable), posted_platform_id (nullable)
- created_at, updated_at

Unique on (lineage_id, version). The latest version of a lineage is the row with the highest `version`.

Rules:
- `content` can change only while status is `WRITING`. After that the row is frozen.
- Every Writer revision, every creator edit and every revision after rejection creates a new version. The replaced version becomes `SUPERSEDED` (or stays `REJECTED` if it was rejected).
- `APPROVED` means this exact version is ready to copy. It requires a decided approval row that references this row's id.
- Editing an approved version creates a new version in `PENDING_APPROVAL`, supersedes the old one, and creates a new approval request. The old approval stays in history and no longer makes anything ready to post.
- `POSTED` is set only on an `APPROVED` latest version, by mark-as-posted, and records that exact version.
- `posted_ref = none` means the creator did not give a URL or platform ID. Such a draft is posted but **unlinked**: the Analyst reports that automated metrics are unavailable until it is linked. Linking later sets `posted_ref`, which is the only change allowed on a `POSTED` row. The Analyst matches by `posted_platform_id` or the ID parsed from `posted_url`, never by title.

### critic_evaluations
- id, draft_id (FK, the exact version reviewed), review_number (1 to 3, counted within the lineage's current review loop)
- score, passed
- rubric_json, deterministic_json, feedback_json, created_at

Unique on (draft_id). One evaluation per version.

### approvals
- id, run_id (FK, nullable: null when the creator edits an approved item outside a run)
- item_type: `plan`, `draft`, `depth_increase`
- item_id (the exact plan version row, draft version row, or run id for `depth_increase`)
- status (`PENDING`, `DECIDED`, `CANCELLED`)
- decision (`APPROVED`, `REJECTED`, `EDITED`; null unless `DECIDED`)
- feedback_text, edited_content (both nullable)
- resulting_item_id (nullable): for `EDITED`, the new version created and approved by this decision
- requested_at, decided_at (nullable)

A `PENDING` row is a paused run waiting for the creator. Index on (status, requested_at). Unique among `PENDING` rows on (item_type, item_id). A request becomes `CANCELLED` when its item is superseded or its run is cancelled. A weekly brief has no approval of its own: the plan linked to the brief uses `item_type = plan`.

### 5.1 Transition rules (authoritative)

All transitions happen in code, in one transaction, with the approval row written first.

| Current state | Action | Result |
|---|---|---|
| Plan `PENDING_APPROVAL` | Approve | Plan `APPROVED`; approval `DECIDED / APPROVED` |
| Plan `PENDING_APPROVAL` | Reject with feedback | Plan `REJECTED`; approval kept; Strategist creates the next version |
| Plan `PENDING_APPROVAL` | Edit and approve (`EDITED`) | New plan version created by `creator`, `APPROVED`; earlier version `SUPERSEDED`; approval records `resulting_item_id` |
| Plan `APPROVED` | Edit | New version `PENDING_APPROVAL` with a new approval request; earlier version `SUPERSEDED` |
| Draft `PENDING_APPROVAL` | Approve | This exact version `APPROVED` |
| Draft `PENDING_APPROVAL` | Reject with feedback | Version `REJECTED`; Writer creates the next version |
| Draft `PENDING_APPROVAL` | Edit and approve (`EDITED`) | Deterministic checks run. If they pass, a new version by `creator` is created and `APPROVED`, and the earlier version is `SUPERSEDED`. If they fail, nothing changes and the error is returned. The Critic is not run again |
| Draft `APPROVED` | Edit | Deterministic checks run, then a new version is created in `PENDING_APPROVAL` with a new approval request; the old version becomes `SUPERSEDED` |
| Draft `APPROVED` (latest) | Mark as posted | That version becomes `POSTED` |
| Draft in any other state | Mark as posted | Rejected with 409 |
| Any item | Decision on a `CANCELLED` or already `DECIDED` approval, or with a non-matching `item_id` | Rejected with 409 `STALE_APPROVAL` |
| Plan linked to a brief | Approve, reject or edit | Same rules as any plan. The brief record is unchanged |
| Depth increase `PENDING` | Approve | Run limits raised for that run only |

---

## 6. Learning and briefs

### performance_metrics
- id, draft_id (FK, the posted version), platform, metric_name, value
- source (`public`, `owner`), collected_at

Unique on (draft_id, metric_name, collected_at).

### analyst_findings
- id, run_id (FK), draft_id (FK, nullable)
- finding, recommendation
- confidence (`low`, `moderate`, `high`), sample_size
- evidence_json, created_at

### strategy_entries
- id, creator_id (FK), key, value_json, reason
- supporting_finding_ids_json
- status (`active`, `superseded`), created_at

Examples of keys: preferred format, target audience, current experiment. A change creates a new row and marks the old one `superseded`, so history is kept.

### weekly_briefs
- id, run_id (FK), trigger (`scheduled`, `manual`)
- period_key (nullable: set only when `trigger = scheduled`, for example `2026-W44`, the ISO week of the scheduled fire time in the creator's time zone)
- content_markdown, plan_id (FK, nullable)
- status: `GENERATED`, `ARCHIVED`
- created_at, read_at (nullable)

Partial unique index on `period_key` where `trigger = 'scheduled'`. This allows at most one scheduled brief per ISO week, including after a catch-up or a mid-week schedule change, and never blocks manual briefs. Manual briefs have no `period_key` and do not count toward the scheduled brief for that week. The plan inside a brief has its own status and approval, so the brief itself has no approval states.

---

## 7. Evaluation data

### evaluation_runs
- id, started_at, finished_at, system_variant (`fixed_pipeline`, `supervisor_graph`), model_name, notes
- model_version, prompt_version, tool_versions_json, fixture_set_version, config_json

These fields make a result reproducible. Both variants of a comparison must record the same model, tools, fixtures and settings.

### evaluation_results
- id, evaluation_run_id (FK), test_case_id
- completed (bool), plan_score, agent_calls, routing_errors, routing_invalid, routing_suboptimal
- duration_seconds, tokens_used, details_json

`routing_invalid` counts choices outside the eligible list. `routing_suboptimal` counts allowed but wrong choices against the labelled expected route. Test case definitions live as fixture files in the repository, not in the database. Results contain scores and fixture IDs only, never creator content, so they can be kept after creator data deletion.

---

## 8. Other storage

- **Checkpoints:** LangGraph SQLite checkpointer, in a separate file (`checkpoints.db`), so application migrations never touch it. Creator data deletion removes checkpoints by the `thread_id` values in `runs`.
- **Scheduler jobs:** the APScheduler SQLAlchemy job store creates and manages its own table.
- **Files:** none in v1. No uploads.

---

## 9. Relationships (summary)

- creator has many goals, content_items, comment_insights, strategy_entries
- goal has many runs
- run has many tasks, routing_logs, token_usage, run_events, research_findings, content_plans, approvals
- content_plan lineage has many versions; each version has many plan_items
- plan_item rows with the same `item_key` across plan versions are one logical item. Drafts link to the item row they were written for and to the `item_key`. A draft lineage has many versions. A repurposed draft points to its approved source version through `parent_draft_id`
- draft version has one critic_evaluation and many performance_metrics
- content_item has many comments
- weekly_brief links to one plan version

---

## 10. Retention and cleanup (confirmed defaults)

A cleanup job runs once at backend startup and then daily at 03:00 in the creator's time zone. It skips any step that touches data used by a run in `RUNNING` and tries again at the next cycle.

- Comment text older than 90 days is cleared (`text` becomes null). The comment row, its counts, dates and `processed_at` marker stay, so insights never depend on re-reading cleared comments and no comment is processed twice. Insights keep no copy of comment text, and their example links stop showing text once it is cleared.
- Superseded `comment_insights` older than 180 days are deleted.
- `cache_entries` are removed after `expires_at`. Fetched pages and transcripts of other creators' content use the cache or a 30-day expiry, and `transcript_text` for `similar` content items is cleared after 30 days. The creator's own transcripts are kept until deletion.
- `run_events` older than 90 days are deleted. `routing_logs` are kept for evaluation until creator data deletion.
- Expired and used `oauth_states` are removed.
- Revoking a platform login deletes its `oauth_tokens` row.
- Completed `evaluation_*` results are kept.

---

## 11. Creator data deletion

Defined in ADR-024 and API.md section 7. The steps, in order:

1. Stop active runs and refuse new runs and briefs until deletion finishes.
2. Delete the local OAuth tokens. Revocation at the provider is attempted on a best-effort basis, and a revocation failure is recorded as a warning and never blocks local deletion.
3. Remove scheduler jobs.
4. Delete checkpoints using the `thread_id` values in `runs`.
5. Delete all application rows for the creator: profile, settings, goals, runs, tasks, routing logs, token usage, run events, content, comments, insights and their source and example links, research findings, plans, drafts, approvals, metrics, findings, strategy, briefs and OAuth states.
6. Delete cache entries.
7. Compact both database files (`VACUUM` and a WAL checkpoint) so deleted content is not left in free pages.

Each step's outcome is recorded in `deletion_jobs.steps_json`. A failed step stops the job as `PARTIAL`, and a retry resumes from that step. Application rows are removed after checkpoints so that the `thread_id` values needed to delete checkpoints are still known if a step must be retried. `evaluation_*` rows and `deletion_jobs` remain because they hold no creator content. Settings, including `onboarding_completed`, are removed in step 5, so the UI shows onboarding again after a completed deletion.

---

## 12. Open points

- Final column types and constraints are fixed when the SQLAlchemy models are written.
- Decided in ADR-032 and ADR-033: stored content is kept when the creator changes channel, and insights are traced to their channel through `comment_insight_sources`.
