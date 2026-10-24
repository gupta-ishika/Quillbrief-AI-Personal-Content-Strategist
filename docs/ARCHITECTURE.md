# ARCHITECTURE: AI Personal Content Strategist

Status: Locked v1.1
Scope of this document: HOW the system is built. Requirements are in PRD.md.
Detailed schemas are deferred: database tables go in DATABASE.md and API contracts in API.md.

---

## 1. System overview

```text
                +---------------------------+
                |        React UI           |
                | goal, approvals, briefs,  |
                | run history, routing log  |
                +-------------+-------------+
                              |  HTTP (REST, polling)
                +-------------v-------------+
                |      FastAPI backend      |
                |  API routes | APScheduler |
                +------+------------+-------+
                       |            |
        +--------------v--+     +---v-----------------------+
        |  LangGraph      |     |  SQLite (SQLAlchemy)      |
        |  agent graph    +-----+  app data + checkpoints   |
        +---+---------+---+     +---------------------------+
            |         |
   +--------v--+  +---v-----------------+      +----------------+
   | MCP tools |  | Custom tools        |      | Ollama         |
   | YouTube,  |  | comments, metrics,  |      | qwen3.5:4b     |
   | search... |  | draft check, DB     |      | nomic embed    |
   +-----------+  +---------------------+      +----------------+
```

Key idea: the language model makes contextual decisions inside the graph. Ordinary code enforces everything that must never be wrong: retry limits, step budgets, approval gates, database writes and credentials.

---

## 2. Technology stack

- **Agent orchestration:** LangGraph (Python).
- **Language model:** Qwen3.5 4B through Ollama (`qwen3.5:4b`).
- **Embeddings:** nomic embedding model through Ollama, used only for comment clustering.
- **Backend:** FastAPI.
- **Database:** SQLite through SQLAlchemy.
- **Checkpointing:** LangGraph SQLite checkpointer.
- **Scheduler:** APScheduler with a SQLAlchemy job store on the same SQLite setup.
- **Tools:** MCP servers loaded through LangGraph's MCP adapter, plus custom Python tools.
- **Frontend:** React. Build tool and styling are set in DESIGN.md.
- **Clustering:** scikit-learn on embeddings. The exact method is tuned during build.

---

## 3. The agent graph

### 3.1 Nodes

- `supervisor`: reads state, maintains the task list, chooses the next node.
- `listener`: understands the creator and audience (ReAct).
- `research`: investigates the niche and similar creators (ReAct).
- `strategist`: builds the content plan.
- `writer`: writes drafts and the Weekly Brief text.
- `critic`: reviews drafts.
- `repurposer`: adapts approved drafts to other formats.
- `analyst`: post-mortem on posted content (ReAct).
- `approval`: pauses the run for the creator's decision.

### 3.2 Edges

Almost every node returns to the Supervisor. The only fixed edges are safety edges:

```text
START -> supervisor
listener | research | strategist | repurposer | analyst -> supervisor
writer -> critic
critic -> writer        (failed and reviews remaining)
critic -> approval      (passed, or reviews exhausted)
approval -> supervisor  (decision and feedback written to state)
supervisor -> END       (all tasks done, or budget reached)
```

This is not a fixed order. The Supervisor can send control to any allowed node at any time.

### 3.3 How the Supervisor decides

Because the model is small, routing is split between code and the model.

1. **Code computes the eligible next nodes** from the state. For example, `approval` is eligible only when a draft or plan is waiting. `writer` is eligible only when an approved plan item has no draft. `listener` is not eligible when fresh comment insights exist.
2. **The model chooses among the eligible nodes** and returns a structured decision: next node, reason, and task list changes. Output uses a JSON schema through Ollama structured output, with thinking off.
3. **Code validates the decision** against the allowlist and the budgets. An invalid answer is retried once, then replaced by a deterministic default.
4. **The decision is logged** in the routing log with the reason and tokens used.

If only one node is eligible, the model is not called.

### 3.4 Rules enforced in code

- If Critic reviews reach 3, stop the revision loop.
- If the step budget for the depth level is reached, stop the run and report what is unfinished.
- If a repeated routing pattern is detected, stop switching and escalate to the creator.
- No draft becomes ready to post without an approval record that references that exact version.
- Saved plan and draft versions are immutable. Edits create new versions (DATABASE.md section 5.1).
- Raising the depth level needs an approval record.
- Database writes happen through tool functions with validation.

### 3.5 ReAct loops

The Listener, Research and Analyst agents run a ReAct loop: the model picks a tool, reads the result, and either picks another tool or finishes. Each loop has a step limit from the depth level. Each agent sees only its own tools.

---

## 4. Shared state

State holds compact summaries and identifiers. Raw comments, transcripts and web pages stay in SQLite.

```python
class ContentState(TypedDict):
    run_id: str
    user_goal: str
    depth_level: str
    task_list: list
    creator_profile: dict
    comment_insights: list
    research_results: dict
    content_plan: list
    current_draft_id: str
    critic_feedback: list
    critic_score: float
    critic_retries: int
    strategy: dict
    performance_insights: dict
    weekly_brief_id: str
    user_feedback: str
    approval_status: str
    next_action: str
    execution_steps: int
    tokens_used: int
```

This is a starting structure. Final fields are set when the Pydantic models are written.

Graph state and persistent storage are different things. State lives during a run and is saved by the checkpointer so a paused run can resume. SQLite tables hold long-term records.

---

## 5. Agents and their tools

Tools are either MCP tools or custom tools. LangGraph treats both the same way.

- **Supervisor:** state and task-list tools only. No external tools.
- **Listener:** YouTube MCP (read-only), comment fetcher, comment clusterer, database tools.
- **Research:** web search MCP, web fetch MCP (through the URL guard, section 14), YouTube MCP.
- **Strategist:** database tools to read insights, strategy history and past plans.
- **Writer:** database tool to save drafts and briefs.
- **Critic:** draft checker, database tool to save evaluations.
- **Repurposer:** database tools. Instagram MCP only to read for context, if available.
- **Analyst:** YouTube MCP and Instagram MCP (read-only), metrics calculator, database tools.
- **Approval step:** approval tool.

### 5.1 Custom tools

- **Comment fetcher:** fetches comments with a cap, prefers recent and highly engaged ones, removes duplicates, spam, emoji-only and very short comments, and returns the coverage count.
- **Comment clusterer:** embeds comments locally, groups them by similarity, and returns theme counts with two or three examples each. No LLM tokens are used.
- **Metrics calculator:** averages, comparisons and sample sizes in code, with a confidence level.
- **Draft checker:** word count, required sections and platform length limits.
- **State and database tools:** save and load plans, drafts, insights, strategy history, briefs and logs.
- **Approval tool:** pauses the run through LangGraph interrupt, and returns the creator's decision and feedback.

### 5.2 MCP servers

- **YouTube:** channel videos, comments, transcripts and analytics. Read-only.
- **Web search** and **web fetch:** niche research and page reading, with capped results.
- **Instagram:** optional and read-only. Needs a Business or Creator account. Used by the Analyst and the Repurposer for the creator's own account only.
- **SQLite:** optional. Critical writes stay in code-controlled tools.

Before an agent is built, each server goes through the MCP checklist (section 11). The decision rule applies: integrate if all checks pass, split between MCP and custom tools if only some tools work, and reject in favor of a custom tool if there are security, maintenance or reliability concerns.

### 5.3 Platform capabilities

Drafting is supported for YouTube, Instagram, LinkedIn and X. Data access is not equivalent: full public research and owner analytics are planned for YouTube only, Instagram analytics are optional, and LinkedIn and X are draft targets with web research only. The matrix is in PRD.md section 5.1. The Analyst reports when no performance data exists for a platform.

---

## 6. Main flows

### 6.1 Goal to approved draft

1. The creator submits a goal and depth level.
2. The Supervisor creates a task list.
3. The Supervisor routes to the Listener and, depending on data, the Research agent.
4. The Strategist builds a plan from comment insights, similar creators and its own ideas.
5. The run pauses at `approval` for the plan.
6. On approval, the Writer drafts each selected item. On rejection, the feedback goes back to the Strategist.
7. The Critic reviews each draft, up to three times.
8. The run pauses at `approval` for each draft.
9. The approved draft is marked ready to copy. The Repurposer can then adapt it to other formats, and those drafts go through the same approval.

### 6.2 Posting and learning

1. The creator posts manually and marks the draft as posted, optionally adding the link or video ID.
2. The Analyst collects performance data for posted content and writes findings with sample size and confidence.
3. The Supervisor routes findings to the Strategist, which updates stored strategy.

### 6.3 Weekly Brief

1. APScheduler triggers the run at the configured day and time (default Monday 08:00, `Asia/Kolkata`). The creator can also start a manual brief.
2. The Supervisor checks what is new: posts, comments, stale research.
3. It calls only the agents needed, for example the Analyst when there are new posts and the Listener when there are new comments.
4. The Strategist drafts next week's plan, and the Writer formats the brief.
5. The brief appears in the UI inbox. The plan inside it waits for approval.

### 6.4 Example routes (for the agentic tests)

- **New creator, two videos:** Listener, then Research, then Strategist.
- **Established creator, fresh insights:** Strategist directly.
- **Plan rejected:** back to the Strategist with feedback.
- **Weak hook in a draft:** Writer and Critic loop.
- **No new posts this week:** the brief skips the Analyst.

---

## 7. Persistence

SQLite holds application data. Table definitions go in DATABASE.md. Planned entities:

- creator profile, goals, runs and tasks
- comment insights and processed comment markers (for incremental runs)
- research findings
- content plans and plan items
- plan and draft versions (each version is a row) and Critic evaluations
- approvals and posted-content records, including unlinked posts
- deletion jobs
- performance metrics
- strategy history with evidence
- weekly briefs
- routing logs and token usage
- encrypted OAuth tokens

LangGraph checkpoints are stored through the SQLite checkpointer. They are kept in a separate database file from application data, so application migrations do not touch them.

---

## 8. Human-in-the-loop

- The `approval` node calls LangGraph interrupt. The run pauses and the checkpointer saves its state.
- The backend exposes pending approvals. The React UI shows the item and the creator approves, rejects with feedback, or edits.
- The backend resumes the run with the decision. This works after a restart because the state is in SQLite.
- Approval types: plan, draft, Weekly Brief plan and depth increase.
- An approved draft version is marked ready to copy. The UI offers a copy action and a mark-as-posted action.
- Every approval request names the exact plan or draft version. The decision must name the same version. If the item was superseded since, the request is `CANCELLED` and the decision is rejected as stale.
- `EDITED` means approve with edits: code runs the deterministic checks, creates a new version authored by the creator, and approves it in the same transaction. The Critic is not run again on creator edits.
- Editing an already approved item creates a new version in `PENDING_APPROVAL` with a new approval request, and the old approval no longer makes anything ready to post.
- A weekly brief has no approval of its own. The plan linked to it is approved, rejected or edited like any other plan.
- The full transition table is in DATABASE.md section 5.1.

---

## 9. Scheduler, credentials and background runs

### Scheduler

- APScheduler runs inside the FastAPI process with a SQLAlchemy job store, so scheduled jobs survive restarts.
- **Schedule source:** the saved settings `brief_day`, `brief_time` and `time_zone` control the Weekly Brief job. The environment values are first-run defaults only. When settings change, the backend replaces the job (cron trigger with a `zoneinfo` time zone) before returning, and reports `next_brief_at`.
- **Onboarding gate:** no Weekly Brief job exists, and the startup catch-up generates nothing, until `onboarding_completed` is true. Schedule changes made during onboarding are only saved. Completing onboarding creates the job from the saved settings, and later changes replace it. After creator data deletion the job is removed and recreated at the next completion.
- **Scheduled period:** each scheduled brief belongs to an ISO week (`period_key`, for example `2026-W44`) computed in the creator's time zone at fire time. The database allows one scheduled brief per `period_key`. If the schedule is changed mid-week and the week already has a scheduled brief, the trigger is skipped and a `note` event is logged.
- **Manual briefs** (`trigger = manual`) have no period. They are allowed whenever no brief run is active, and they do not count toward or block the scheduled brief.
- **Catch-up:** on startup the backend finds the latest scheduled fire time that has passed without a brief. If one exists it runs once. Earlier missed periods are not generated. Repeated checks cannot create duplicates because of the unique `period_key`.
- **Overlap:** the job allows one instance at a time and coalesces missed fires. If a scheduled brief is still running when the next trigger fires, the new trigger is skipped and logged.
- **Time zones:** daylight-saving changes and time-zone setting changes recompute the next fire time. They must never create two scheduled briefs for the same week.
- **Cleanup** runs at startup and daily (DATABASE.md section 10).

### Credentials

- Public data uses an API key stored in a `.env` file that stays out of version control. It is read through configuration only, never accepted or returned by the API (ADR-021).
- Owner-only metrics use OAuth with read-only scopes.
- The refresh token is stored encrypted in SQLite using Fernet from the Python `cryptography` library. The encryption key is an environment variable. Access tokens are held in memory only and refreshed on demand.
- The OAuth flow uses a single-use `state`, checks granted scopes, and handles denial and refresh failure (SECURITY.md section 2). A refresh failure sets the credential to `needs_reauth`, and tools return a structured error instead of crashing the graph.
- Tokens are read only inside tool code. They never enter prompts, state, logs or redirects.

### Background execution

- Runs execute in a background worker inside the backend, not in the request handler.
- The UI polls run status. A single user does not need a queue or separate worker service in v1.
- Cancellation is cooperative. A flag is checked at every step boundary. A tool call already in progress finishes or times out and its result is discarded. No node writes after cancellation except the final status.

---

## 10. Token and cost control

Each run follows its depth level. Numbers are starting values to tune after measuring the model.

- **Quick:** last 5 videos, up to 300 comments, 3 searches and 3 pages, 4 tool-loop steps per agent, 2 Critic reviews, 15 Supervisor steps.
- **Standard (default):** last 10 videos, up to 1,000 comments, 6 searches and 6 pages, 6 tool-loop steps, 3 Critic reviews, 30 Supervisor steps.
- **Deep:** last 25 videos, up to 3,000 comments, 12 searches and 12 pages, 10 tool-loop steps, 3 Critic reviews, 50 Supervisor steps.

Additional controls:

- Per-call input limits: Supervisor 1,500 tokens, Listener 4,000, Research 6,000, Strategist 6,000, Writer 4,000, Critic 3,000.
- Tools return capped results. Raw data stays in the database.
- After the first run, only new comments are processed.
- Every node logs its token use.
- Research results and transcripts are cached.
- The Weekly Brief runs at Standard. Deep runs only on request.
- Outputs always report coverage.

---

## 11. MCP server checklist

Each server must pass these checks before it is integrated:

- It exists and is maintained, with recent updates, a clear licence and an active repository.
- It exposes the tools we need: for YouTube, comments with paging, transcripts and analytics.
- Authentication works with read-only scopes and keeps credentials out of the model's context.
- It works with LangGraph's MCP adapter, including its transport.
- Its limits fit our depth levels, such as quotas and rate limits.
- Output size can be capped. If not, wrap it in a custom tool that trims results.
- It is safe to run. Community servers run with our credentials, so the source is reviewed first.
- Failure behavior: it returns controlled errors for unavailable data, quota exhaustion and timeouts.
- Provenance: each result identifies its source, timestamp and the platform or video ID.
- Permission boundaries: it can be restricted to exactly the tools the agent needs, and cannot reach our credentials or other tools.
- The approved version and the review result are recorded in DECISIONS.md.

Check specifically how transcripts are obtained, because the official YouTube API may restrict caption downloads to the video's owner. This covers other creators' videos and the connected creator's own videos. For the own-video case, record which OAuth scopes are needed and do not assume they are compatible with the read-only rule (ADR-009) until verified.

A custom tool is a fallback only for MCP problems of quality, security or maintenance. It cannot bypass a restriction of the official API. If the API does not provide the data, the system returns a partial result or says the data is unavailable.

---

## 12. Error handling

- Every external call has a timeout and bounded retries.
- A failing tool returns a structured error. The agent can try another tool or finish with a partial result.
- Invalid Supervisor output is retried once, then replaced by a deterministic default. The routing log records the invalid-output category, whether the retry worked and whether the fallback was used. A run that used a fallback or lost a required tool is marked `degraded` with a reason, and the UI shows it instead of presenting the run as fully successful.
- A failed or stopped run keeps its state and log, and the UI shows what is unfinished.
- Duplicate work is avoided by tracking completed tasks in state.
- If Ollama becomes unavailable during a run, the run becomes `INTERRUPTED` after bounded retries and can be resumed.
- A tool failure is never worked around by bypassing a platform restriction. The agent uses an approved alternative source, returns a partial result or says the data is unavailable.

### 12.1 Run recovery

At backend startup, before accepting requests:

1. Runs in `WAITING_APPROVAL` are left alone. Their pending approvals and checkpoints are preserved.
2. Runs in `RUNNING` are set to `INTERRUPTED` and a `recovery` event is recorded. They are not resumed automatically, because the creator may not want a long model run to start unprompted.
3. The creator resumes an interrupted run (`POST /runs/{id}/resume`) or cancels it. Resume continues from the last checkpoint. Tasks marked `DONE` are not repeated.
4. Database writes made by tools are idempotent. Each write uses a natural key such as (run, step, tool) or a content hash, so re-running the interrupted node does not create duplicate plans, drafts or findings.
5. Each node saves its results and its step marker in one transaction, so a crash leaves either the whole step or none of it.
6. Pending approvals never become approved by recovery.

---

## 13. Evaluation architecture

- A fixed-pipeline graph lives in its own module as the baseline. It runs the same nodes in a set order, with the same tools, input data, model settings and output requirements as the Supervisor graph. Only the routing differs.
- Each evaluation run records the model version, prompt version, tool versions, fixture set version and configuration, so results can be reproduced and compared.
- Routing is scored twice. **Validity:** was the chosen node on the eligible list? **Quality:** was it the right choice for that state, judged against labelled expected routes in the fixtures? An allowed but wasteful choice, such as repeating fresh research, counts as suboptimal. The labels and scoring rules are written before the comparison script (EVAL-02).
- Test cases are fixtures with a goal, a starting state and sample data. The starting states cover the cases in section 6.4.
- A comparison script runs both graphs on every test case and records completion, plan quality scores, agent calls, routing errors, time and tokens.
- Critic scores are checked against a human-reviewed sample.
- Results are saved so changes to prompts or models can be compared over time.

---

## 14. Security and privacy

- Only read-only access is requested from any platform.
- Secrets are never placed in prompts, state, logs, redirects or version control.
- Comment data keeps only text, likes, reply count and date. Usernames and reply text are not stored.
- Community MCP servers are reviewed before use.
- The system has no capability to publish, schedule or send content to external platforms, so there is no write path to external accounts. The internal scheduler only triggers local work.
- **Local API:** loopback binding, a single allowed CORS origin, Origin checks on state-changing requests, a Host check on every request (a loopback name with the configured backend port), and JSON-only bodies (API.md section 1).
- **URL guard:** the fetch tools allow only http and https, resolve the host first and refuse loopback, private, link-local, multicast, reserved and metadata addresses, repeat the check on every redirect, and cap time and size.
- **Deletion:** one service deletes tokens, scheduler jobs, checkpoints, cache and application rows in a defined order and reports each step (ADR-024).

---

## 15. Repository layout (proposed)

```text
backend/
  app/
    api/            routes
    graph/          nodes, edges, supervisor, state
    agents/         one module per agent
    tools/          custom tools and MCP loader
    db/             models, migrations
    scheduler/      APScheduler setup
    evaluation/     fixed pipeline, fixtures, compare script
  tests/
frontend/
  src/
docs/
  PRD.md
  ARCHITECTURE.md
```

---

## 16. Open points

- Model test result for qwen3.5:4b and any change that follows.
- Onboarding is specified in PRD.md FR-0 and DESIGN.md section 4.0 (ADR-030, ADR-031).
- Results of the MCP server checks.
- Clustering method and thresholds for comment themes.
- Number of evaluation test cases.
- Final state and Pydantic models, finalized in API-00 and the graph tasks (GRAPH-01) from the locked DATABASE.md and API.md.

---

## 17. Next documents

DATABASE.md, API.md, DESIGN.md, RULES.md and TASKS.md follow after PRD.md and ARCHITECTURE.md are reviewed and locked.
