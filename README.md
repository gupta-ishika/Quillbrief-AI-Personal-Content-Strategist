# AI Personal Content Strategist

A local, multi-agent system that helps a content creator decide what to post, draft the content, check its quality, and learn from the results to improve the next plan.

It is not a chatbot that writes on request. A Supervisor agent breaks a goal into tasks, picks which specialized agent acts next based on the current state, and loops back when results are weak or the creator gives feedback.

**The system never publishes.** It stops at approved drafts. You copy and post them yourself, then mark them as posted so the system can learn from the results.

Status: planning complete (draft documents). Implementation has not started.

---

## What it does

- **Listens** to your videos and comments and finds recurring audience questions and requests.
- **Researches** your niche and similar creators to find gaps.
- **Plans** content from three sources: your comments, similar creators, and its own ideas. Each idea shows why it was suggested.
- **Writes** scripts, titles, descriptions, community posts, captions, LinkedIn posts and X threads.
- **Reviews** each draft with a Critic, with a limit on revisions.
- **Learns** from performance data and uses the findings in the next plan.
- **Sends a Weekly Brief** on a schedule you set (default Monday 08:00 in the Asia/Kolkata time zone) in the app. You can also run one on demand.
- **Asks for approval** at every important step.

---

## How it is built

- **Orchestration:** LangGraph (Supervisor, ReAct loops, interrupt for approvals)
- **Model:** Qwen3.5 4B through Ollama. Comment embeddings use a nomic embedding model, locally.
- **Backend:** FastAPI, SQLite (SQLAlchemy, Alembic), APScheduler
- **Tools:** MCP servers where they pass the checks, plus custom Python tools
- **Frontend:** React

Version 1 covers planning, drafting, review, repurposing for YouTube, Instagram, LinkedIn and X, performance analysis, and the Weekly Brief.
Version 2 adds the Brand-Deal Inbox and the Creator Collab Matchmaker.

---

## Documents

Read them in this order.

- `docs/PRD.md`: what we are building and why
- `docs/ARCHITECTURE.md`: how it works
- `docs/DATABASE.md`: tables and rules
- `docs/API.md`: backend endpoints
- `docs/DESIGN.md`: how the UI should look and behave
- `docs/RULES.md`: rules for anyone writing code, human or AI
- `TASKS.md`: phased task list
- `docs/TEST_PLAN.md`: how we check that it works
- `docs/SECURITY.md`: security requirements and the release checklist
- `docs/DECISIONS.md`: permanent decisions and spike results
- `docs/MEMORY.md`: current project state

---

## Requirements (planned)

- Python 3.11 or newer
- Node.js LTS and npm
- Git
- Ollama, with `qwen3.5:4b` and `nomic-embed-text` pulled
- A YouTube Data API key for public data
- Optional: read-only Google OAuth for owner-only analytics, and an Instagram Business or Creator account

---

## Setup (to be confirmed when the code exists)

1. Copy `.env.example` to `.env` and fill in the values. The YouTube API key is set only in `.env`. The app shows whether it is configured but never accepts or displays it. To change it, edit `.env` and restart the backend.
2. Pull the models: `ollama pull qwen3.5:4b` and `ollama pull nomic-embed-text`.
3. Install the backend dependencies and run the database migrations.
4. Start the backend.
5. Install the frontend dependencies and start the frontend.
6. Open the app, finish the first-run setup (niche, tone, optional YouTube channel), check the health screen, and enter a goal.

Exact commands are added in task REL-02 after the project is built.

---

## Repository layout (planned)

```text
backend/
  app/
    api/  graph/  agents/  tools/  db/  scheduler/  evaluation/
  tests/
frontend/
  src/
docs/
README.md
TASKS.md
.env.example
.gitignore
```

---

## Project workflow

For every task: read the documents, plan, implement, test, review, fix, commit, then update TASKS.md, MEMORY.md and any affected document.

---

## Limits and honesty

- The system supports better-informed decisions. It does not guarantee audience growth.
- A small local model is less reliable than a large one. Early tests decide whether it is good enough.
- Features are described as built only after they are built and tested.
