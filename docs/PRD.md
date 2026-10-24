# PRD: AI Personal Content Strategist

Status: Locked v1.1
Scope of this document: WHAT we are building and WHY. The HOW is in ARCHITECTURE.md.

---

## 1. Overview

The AI Personal Content Strategist is a multi-agent system that helps a content creator decide what to post, draft the content, check its quality, and learn from the results to improve the next plan.

It is not a chatbot that generates text on request. A Supervisor agent breaks a creator's goal into tasks, chooses which specialized agent should act next based on the current state, and loops back when results are weak or the creator gives feedback. Performance data and creator feedback change the next plan.

The system always stops at approved drafts. The creator posts the content manually. The system never publishes.

---

## 2. Problem

A solo creator, for example someone who publishes coding tutorials, usually faces these problems:

- They do not know which topics their own audience wants.
- They do not know what similar creators are covering or where the gaps are.
- They struggle to keep a consistent content plan.
- Writing scripts, hooks, titles, descriptions and posts takes a lot of time.
- Content must be adapted for several platforms.
- They rarely review why some content performed well, so lessons are lost.
- Even when they learn what works, they do not always change the next plan.
- Each week they must collect comments, analytics and competitor activity by hand.

---

## 3. Goals and non-goals

### Goals

- G1. Turn a goal written in plain language into a reviewed content plan and drafts.
- G2. Build the plan from three sources: the creator's own audience comments, what similar-niche creators are doing, and the system's own ideas.
- G3. Improve draft quality through a Critic and Writer loop with a limit on revisions.
- G4. Learn from performance data and use the findings in later plans.
- G5. Deliver a Weekly Brief every week on the creator's configured schedule (Monday at 08:00 `Asia/Kolkata` by default).
- G6. Be genuinely agentic: the execution path depends on the situation and is not a fixed pipeline.
- G7. Keep the creator in control through human approval at every important step.
- G8. Run locally on a small model (Qwen3.5 4B through Ollama) within a controlled token budget.

### Non-goals

- The system does not publish, schedule or send content to any external platform. Its internal scheduler may trigger local analysis and Weekly Brief generation.
- The system does not spend money, run ads or change any external account.
- The system does not fine-tune or train a model. It adapts by updating stored strategy and context.
- The system does not guarantee audience growth. It supports better-informed decisions.
- The system does not generate video, audio or images.

---

## 4. Users

**Primary user:** a solo creator who publishes regularly and manages their own content.

**Demo niche:** coding tutorials (for example Python and FastAPI). The design must not hard-code this niche.

**Single-user system in v1.** There are no teams, roles or multi-tenant features.

---

## 5. Scope

### Version 1 (build first)

First-run onboarding, Supervisor, Listener, Research, Strategist, Writer, Critic, Repurposing, Post-Mortem Analyst, Weekly Brief, human approval through a React UI, depth levels and token budget, and an evaluation harness.

Content platforms covered by drafts: YouTube (including Shorts and community posts), Instagram (Reel captions), LinkedIn and X.

### Version 2 (planned, not dropped)

- **Brand-Deal Inbox:** triages brand and sponsorship emails through a Gmail MCP server and drafts replies for approval.
- **Creator Collab Matchmaker (Collab Scout):** finds similar-niche creators who would make good collaboration partners and drafts outreach for approval.

### Not planned

- Automatic publishing or scheduling. If it is ever added, it needs its own PRD section and approval controls.

---

### 5.1 Platform capabilities (v1)

Drafting for a platform does not mean the system can read data from it.

| Platform | Draft generation | Public research data | Owner analytics | Credentials |
|---|---|---|---|---|
| YouTube | Yes | Yes, within API quota | Yes, where the API supports it | API key for public data. Read-only OAuth for owner metrics |
| Instagram | Yes | No | Optional, read-only, Business or Creator account | Optional OAuth |
| LinkedIn | Yes | No (web research only) | No | None |
| X | Yes | No (web research only) | No | None |

When data is unavailable for a platform, the system says so and works without it. Exact capabilities are confirmed by the MCP checks before implementation.

---

## 6. Functional requirements (v1)

### FR-0 First-run onboarding

On first launch (`onboarding_completed` is false) the creator completes a short setup of four steps. It collects only what the first run needs and never asks for the YouTube API key.

**Step 1: Niche.** Required free text, trimmed, 1 to 200 characters. Not limited to preset niches.

**Step 2: Tone.** One required preset (Professional, Friendly, Educational, Conversational, Humorous) and optional free-text tone instructions of up to 500 characters.

**Step 3: YouTube channel (optional).**
- Path A, no login: the creator enters a handle (`@name`), a channel ID (`UC...`) or a channel URL. URLs are parsed locally for a handle or ID and are never fetched. Only `youtube.com/@handle` and `youtube.com/channel/<ID>` forms are accepted. Other forms (`/c/`, `/user/`, short links) are rejected with a message asking for a handle or ID. The backend resolves the identifier with the YouTube Data API using the key from `.env`, and the creator confirms the channel title returned.
- Path B, with login: the creator connects YouTube through the read-only OAuth flow and picks their channel from the channels on that account. A channel chosen this way is saved as verified.
- If the API key is not configured, Path A saves the parsed identifier as unverified, and the screen says it will be checked once the key is configured. Path B is unaffected.
- The step explains the dependencies. Identifying a channel does not fetch anything by itself. Public video and comment data needs a configured API key and API support for the requested data. Owner-only analytics need the OAuth connection.
- The step can be skipped. The skip is saved on the server, so the creator resumes at Review. Without a channel, drafting works for all four platforms (ADR-025), but channel-based listening and analysis are unavailable, and the system says so.

**Step 4: Review and finish.** Shows niche, tone, channel and its status (verified, unverified, none), YouTube login status, YouTube API key status (read-only "Configured" or "Not configured" with the `.env` hint), and the Weekly Brief schedule and time zone, seeded from the first-run defaults (Monday 08:00, `Asia/Kolkata`, ADR-022). The creator can change the schedule here or later in Settings. "Finish setup" sets `onboarding_completed`, creates the scheduler job from the saved settings and opens Home. No run starts automatically.

**Persistence and flow rules**
1. Each step is saved to settings when completed. If the creator leaves before "Finish setup", including through the OAuth redirect, onboarding resumes at the first incomplete step with earlier values intact. Skipping the optional channel step does not complete onboarding, and the skip is saved on the server (`onboarding_channel_skipped`), so a creator who skipped resumes at Review rather than at the channel step. After "Finish setup" succeeds, later launches open the main app directly.
2. `onboarding_completed` is set only by "Finish setup". Until then, runs and manual briefs are refused, and no scheduler job exists, so no brief is generated.
3. After `DELETE /creator/data` completes, settings are gone and onboarding appears again. While deletion is running, onboarding is unavailable (409 `DELETION_IN_PROGRESS`).
4. The OAuth callback redirects the browser to the onboarding screen with a status only (success, denied or error). It never carries tokens, codes or state (ADR-027).

**Validation.** All of the following are enforced server-side. Niche is trimmed, not empty, 1 to 200 characters. Tone preset is one of the five presets. Tone instructions are trimmed, optional, up to 500 characters. Control characters are rejected, except newlines in tone instructions. Frontend checks are only for convenience. Channel identifiers are validated against the accepted formats before any API call.

**Prompt handling.** Niche and tone instructions are untrusted data. They go into prompts only inside a marked data section, with the instruction not to follow anything inside it (RULES.md section 4).

**Creator profile.** The Writer and Critic receive one profile object built in code from settings: `niche`, `tone_preset`, `tone_instructions` and `profile_source = "declared"`. In v1 it holds declared preferences only (ADR-030).

**Not in onboarding:** platform selection (drafting for all four platforms needs no setup), API key entry, style analysis, publishing or scheduling content.

**Acceptance criteria**
1. A new creator can finish setup with niche and tone alone.
2. Over-length or empty niche and tone are rejected by the backend with the standard error shape.
3. Handle, channel ID and supported URL forms resolve. Unsupported URL forms are rejected without any network request.
4. Skipping the channel step or OAuth does not block completion.
5. Closing the browser mid-setup, or the OAuth redirect, loses no completed step.
6. `onboarding_completed` is false until "Finish setup".
7. Onboarding reappears after data deletion, and "Finish setup" recreates the scheduler job.
8. No API key is requested, shown or stored. Only its status appears.
9. Onboarding never publishes, schedules or sends content externally.
10. A creator who finishes onboarding with no channel can still start goals and runs.
11. Skipping the channel step survives closing and reopening the app, and resumes at Review.

---

### FR-1 Goal input

- The creator enters a goal in natural language, for example: "Grow my Python tutorial audience this month. Focus on practical projects."
- The creator can choose a depth level: Quick, Standard (default) or Deep.
- The goal and depth level are stored with the run.

### FR-2 Listener

- Reads the creator's existing videos, titles, descriptions, transcripts where available, and comments.
- Produces creator context: audience level and topics already covered. This is separate from the declared creator-profile object (FR-0, ADR-030), which holds only niche, tone preset, tone instructions and `profile_source`. Inferring style from existing content is not part of v1.
- Produces comment insights: recurring questions, requests, confusion points, praise and complaints, each with a count and two or three example comments. Examples are shown only while the comment text is retained (90 days).
- Reports coverage, for example "450 of 10,240 comments analysed".
- Does not send raw comment lists to the language model.

### FR-3 Research

- Investigates the niche: current topics, audience problems, new tools and gaps in existing content.
- Investigates similar-niche creators: their recent content, formats and what is gaining attention.
- Returns content opportunities, each with a reason and source links.

### FR-4 Strategist

- Produces a content plan from three sources: comment insights, similar-creator activity and its own ideas.
- Each plan item has: topic, format, platform, objective, reason, and its source (comment, similar creator or own idea).
- Uses stored strategy and performance findings when they exist.
- Revises the plan when the creator rejects it, using the feedback and not starting over.

### FR-5 Writer

- Produces drafts for selected plan items: scripts, hooks, titles, descriptions, community posts, captions, LinkedIn posts and X threads.
- Follows the creator's tone, the target format and any Critic instructions.

### FR-6 Critic

- Scores each draft against a rubric: hook, tone, accuracy, length and relevance.
- Runs deterministic checks: word count, required sections and platform length limits.
- Returns a pass or fail result with specific revision instructions.
- A draft is reviewed at most three times. If it still fails, the best version moves to approval with its remaining issues stated.

### FR-7 Repurposing

- Converts an approved long-form draft into other text formats: YouTube Shorts script, community post, description with chapters, Instagram Reel caption, LinkedIn post and X thread.
- Each format follows its platform's length limits and conventions and preserves the technical meaning.
- Each repurposed draft goes through approval like any other draft.

### FR-8 Post-Mortem Analyst

- Runs for content the creator has marked as posted (see FR-11). Content marked as posted without a link or ID is reported as unlinked, and the Analyst says automated metrics are unavailable for it until it is linked.
- Collects available performance data and explains why the content performed as it did.
- Findings include sample size and a confidence level, and distinguish correlation from causation.
- Writes findings to stored strategy so the Strategist can use them.

### FR-9 Weekly Brief

- Runs automatically once per week at the creator's configured day and local time. The default is Monday 08:00 in the `Asia/Kolkata` time zone. The creator can change the day, time and time zone in Settings, and the change takes effect immediately.
- At most one scheduled brief is created per week. If several scheduled runs were missed while the computer was off, only the latest overdue brief is generated. If a scheduled brief is still running when the next trigger fires, the trigger is skipped.
- The creator can also request a brief at any time. A manual brief is separate from the scheduled one: it does not count toward it and does not block it.
- Contains: what worked and what did not, new comment themes, similar-creator moves worth noting, a recommended plan for next week with reasons, and open decisions.
- Is delivered in the React UI as an inbox item.
- The plan inside the brief needs the creator's approval before it becomes active.
- The Supervisor decides what to include. For example, it skips the post-mortem when nothing new was posted.

### FR-10 Strategy memory

- Strategy, findings and their supporting evidence are stored and reused in later runs.
- Each stored strategy change records why it was made.

### FR-11 Mark as posted

- After approving a draft, the creator copies it and posts it manually.
- The creator then marks the exact approved version as posted and can add the link or video ID.
- If no link or ID is given, the draft is posted but unlinked. The creator can add the link later.
- The Analyst identifies posted content by URL or platform ID, never by title alone.
- This is the link between approved drafts and performance analysis.

### FR-12 Run history and routing log

- The creator can see each run: which agent ran, in what order, why the Supervisor chose it, and the tokens used.
- A run in which a Supervisor decision fell back to the code default, or a required tool failed, is marked as degraded and the UI says why.

### FR-13 Depth levels and token budget

- Each run follows its depth level limits for videos, comments, searches, pages, tool-loop steps, Critic reviews and Supervisor steps.
- A run never exceeds its limits. If the Supervisor decides the data is too thin, it may propose a higher depth, and the creator must approve it.

### FR-14 Evaluation harness

- A fixed-pipeline version of the system exists only as a baseline.
- Both versions run on the same test cases and are compared on the metrics in section 9.

### FR-15 Access and credentials

- Public data (videos, public statistics, comments) is read with an API key.
- Owner-only metrics (watch time, retention, click-through rate) use read-only OAuth, where the creator grants access.
- When owner-only metrics are not available, the Analyst works with public metrics and says so.

---

### FR-16 Versions and approval integrity

- Plans and drafts are saved as versions. Every edit, revision and rejection-driven rewrite creates a new version. Saved versions are not changed.
- An approval refers to one exact version. Editing an approved version invalidates its approval for the new text. The new version needs checks and approval before it is ready to post.
- Creator edits are checked by the deterministic checker (length, required sections, platform limits). They are not sent back to the Critic.
- A decision submitted for an outdated version is rejected.
- Mark as posted records which approved version was posted.

### FR-17 Creator data deletion

- The creator can delete all stored data from Settings, after typing a confirmation phrase.
- Deletion removes OAuth tokens, scheduler jobs, LangGraph checkpoints, cached content and all application records, and then compacts the database files.
- The result is reported per step. A partial failure is shown as partial, never as success, and can be retried.
- Evaluation results and the deletion job record are kept, because they hold no creator content.

---

## 7. Agentic requirements

The system must not be a hidden fixed pipeline. These requirements are testable.

- **AG-1 Dynamic routing.** After each agent finishes, control returns to the Supervisor, which chooses the next step from the current state.
- **AG-2 Goal decomposition and replanning.** The Supervisor turns the goal into a task list and can add, remove or reorder tasks when results change.
- **AG-3 Tool selection.** The Listener, Research and Analyst agents choose their own tools in a ReAct loop and decide when they have enough information.
- **AG-4 Reflection loop.** The Critic and Writer iterate within the retry limit.
- **AG-5 Feedback as a routing signal.** Creator rejections and edits are sent to the agent that should handle them.
- **AG-6 Performance feedback.** Analyst findings change what the Strategist plans next.
- **AG-7 Skip and repeat.** An agent is skipped when its output is fresh and repeated when its output is stale or too thin.
- **AG-8 Controlled autonomy.** Approval gates, retry limits, step budgets and database writes are enforced in code and cannot be bypassed by the model.

**Proof of agentic behavior.** The same system given different starting states must take different routes. The test set includes at least: a new creator with little history, an established creator with rich comments, a rejected plan, a failing draft, thin data, and a Weekly Brief with no new posts.

---

## 8. Human approval requirements

- **HI-1** The creator approves the content plan before drafts are written.
- **HI-2** The creator approves each final draft version before it is marked ready to post.
- **HI-3** The creator approves the plan portion of each Weekly Brief.
- **HI-4** The creator can approve, reject with feedback, or edit.
- **HI-5** A paused run resumes after the creator responds, even hours later, and survives a restart.
- **HI-6** Approved drafts are shown as ready to copy. The system never posts them.
- **HI-7** Raising a run's depth level needs the creator's approval.
- **HI-8** An approval applies to one exact version. Editing approved content creates a new version that needs its own approval, and a decision on an outdated version is rejected.

---

## 9. Success metrics and evaluation

The main experiment: run the fixed pipeline and the Supervisor-based system on the same inputs and test cases, and compare.

- Task completion rate.
- Content plan quality, judged against a fixed rubric by a human reviewer.
- Unnecessary agent calls and routing errors.
- Average execution time and tokens per run.
- Critic score improvement from first draft to final draft, with a sample checked by a human, because the Critic is also a model.
- Share of drafts accepted after the first review, average number of revisions, and share that reach the retry limit.
- Weekly Brief quality, judged by a human reviewer.
- Comment insight coverage: whether themes match what a human finds in a sample of comments.
- Strategy effectiveness, where enough data exists. Differences are not credited to the system alone, because topic, timing and audience size also matter.

Targets are set after the first baseline run. The number of test goals and starting states is to be chosen.

---

## 10. Non-functional requirements

- **Local-first.** Language model: Qwen3.5 4B through Ollama. Comment embeddings: nomic embedding model, running locally.
- **Token control.** Each LLM call stays under about 6,000 input tokens. Raw data stays in the database and is summarized before it reaches a model.
- **Reliability.** Every external call has a timeout and bounded retries. Failures return partial results with clear messages.
- **Resumability.** Interrupted or paused runs resume from saved state.
- **Security.** Secrets stay out of version control, prompts, shared state and logs. OAuth tokens are encrypted at rest. Only read-only scopes are requested.
- **Privacy.** Store only comment text, like counts, reply counts and dates. Usernames and reply text are not needed and are not stored.
- **Auditability.** Routing decisions, tool results, approvals and errors are logged.

---

## 11. Decisions made

- Orchestration: LangGraph, with a Supervisor agent and ReAct loops in the Listener, Research and Analyst agents.
- Human approval: LangGraph interrupt with a checkpointer, and a React UI.
- Tools: MCP servers where they pass the checks, and custom tools otherwise.
- Backend: FastAPI.
- Database: SQLite through SQLAlchemy.
- Scheduler: APScheduler inside the backend.
- Model: Qwen3.5 4B (qwen3.5:4b).
- Embeddings: nomic embedding model.
- Weekly Brief: automatic and configurable, Monday 08:00 `Asia/Kolkata` by default, shown in the UI. Manual briefs are separate from the scheduled one.
- Publishing: none. Drafts stop at approval.
- Onboarding: niche, tone and an optional YouTube channel, saved step by step. No platform selection. The creator profile passed to the Writer and Critic holds declared preferences only in v1 (ADR-030, ADR-031).
- Evaluation: fixed pipeline compared with the Supervisor graph.
- MCP decision rule: if a server passes all checks, integrate it. If only some tools work, use it for those and build the rest as custom tools. If there are security, maintenance or reliability concerns, reject it and build a custom tool on the official API.

---

## 12. Assumptions, risks and dependencies

- **Small model reliability.** A 4B model may choose tools or routes poorly. Mitigation: thinking off for routing, structured output for Supervisor decisions, short tool lists, and code making obvious decisions. If it fails the early test, try a larger model from the same family.
- **Data access.** Public data is limited. Owner-only metrics need the creator's login. Instagram data needs a Business or Creator account and is optional. Drafting for Instagram works without it.
- **Transcripts.** The official YouTube API may restrict caption downloads to the video's owner, so other creators' transcripts may need another source.
- **MCP servers.** Each server may be missing, unmaintained or incomplete. Mitigation: the decision rule in section 11.
- **Critic bias.** The Critic is a model and its scores are not objective. Mitigation: deterministic checks and human review of a sample.
- **Weak analytics.** Small samples give weak conclusions. The Analyst reports sample size and confidence.
- **Scheduler availability.** The scheduled brief needs the backend to be running. A catch-up check on startup generates the latest overdue brief once.
- **Crashes.** A run left `RUNNING` by a crash becomes `INTERRUPTED` at startup. The creator resumes it from its last checkpoint or cancels it.

---

## 13. Open items

- Run the model test: routing decisions, tool selection, no-tool precision and structured output with qwen3.5:4b.
- Run the MCP server checks and apply the decision rule to each server.
- Choose the number of evaluation test cases.
- Choose the clustering method for comment themes during build.
- Confirm that the YouTube Data API supports channel lookup by handle before the channel resolve endpoint is built (MCP-01).
- Review the ADR-015 depth levels and token limits after MODEL-01, and revisit channel-handle resolution (ADR-031) after MCP-01.
- Observed-style analysis of the creator's content is deferred until MODEL-01 and MCP-04 are done (STYLE-01, ADR-030).

---

## 14. Related documents

- ARCHITECTURE.md: system design, graph, state, tools, data flow.
- Next in the flow: DATABASE.md, API.md, DESIGN.md, RULES.md, TASKS.md.
