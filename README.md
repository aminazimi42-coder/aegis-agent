<div align="center">

<img src="docs/assets/aegis-hero.svg" alt="Aegis Agent — Multi-Agent SaaS Orchestration Platform" width="100%"/>

# AEGIS AGENT
### Multi-Agent SaaS Orchestration Platform

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API%20Ready-009688)](https://fastapi.tianglia.com/)
[![License](https://img.shields.io/badge/License-Proprietary-purple)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-Passing-success)](https://github.com/)
[![Status](https://img.shields.io/badge/Status-1.0.0--rc1-7c5cff)](https://github.com/)

[Quick Start](#quick-start) · [Agents](#the-six-agents) · [Twin Loop](#cognitive-twin-loop) · [API Surface](#api-surface) · [Testing](#testing)

</div>

---

## What This Repo Actually Does

Aegis Agent is a **multi-agent SaaS orchestration platform** built on **Python 3.11** and **FastAPI**.
It defines six specialist agents and a cognitive-twin loop that ingests events, evolves a tenant
profile, and proposes actions a human must approve before any execution runs.

The default LLM provider is **EchoProvider** — an offline echo that returns a deterministic stub
response. No paid LLM provider is wired in this revision. If `AEGIS_LLM_PROVIDER` is not set,
`get_provider()` returns `EchoProvider()`.

Persistence is **SQLite** stored under the `AEGIS_DATA_DIR` directory (defaults to `data/`).

---

## The Six Agents

The platform registers six agents in `core/agent_registry.py`:

| Agent | Role | Scope |
|-------|------|-------|
| **Alina** | Strategic Orchestrator | Multi-task batching, policy-driven routing, priority alignment |
| **Kian** | Execution Specialist | Runtime flow control, task dispatch, retry/backoff, SLA enforcement |
| **Bita** | Insight Architect | Telemetry analysis, signal extraction, risk profiling, dependency synthesis |
| **Aylin** | Quality & Validation | Deterministic validators, test-harness orchestration, release sigils |
| **Ahmad** | Security & Oversight | Security-scan orchestration, sandboxing, audit-trail management |
| **Amin** | Finance-Domain Specialist | In-process finance-domain logic — **not** a payment processor |

> **Important:** Amin handles finance-domain modelling and executive-toggle logic in-process.
> It does **not** process payments, settle invoices, or connect to any payment gateway.
> No billing, charging, or settlement runs in this revision.

---

## Cognitive Twin Loop

The platform's headline feature is a **cognitive-twin loop** that builds and evolves a per-tenant
profile. The loop as implemented today (T01–T07) is:

1. **Day-0 interview + consent** — `POST /api/v1/twin/session/start` opens an interview session;
   answers are collected and committed with explicit consent.
2. **Event ingest** — `POST /api/v1/twin/events` ingests a work event (source, kind, payload) and
   deterministically evolves the tenant profile.
3. **Deterministic evolve** — `core/twin_evolution.py` applies the event to the profile and
   persists the result to SQLite.
4. **Weekly digest** — `GET /api/v1/twin/digest/{tenant_id}` produces a summary digest.
5. **Local git observer** — `POST /api/v1/twin/observe/git` reads recent commits from a local repo
   path and feeds them into the twin as events.
6. **Proposed actions with human approve-before-execute** — `POST /api/v1/twin/actions/propose`
   generates candidate actions from the profile + digest. Each action must be **approved** by a
   human (`/approve`) before it can be **executed** (`/execute`). Execution records a row in SQLite
   and the evidence ledger only — it does not perform external writes.

All twin data is persisted in SQLite under `AEGIS_DATA_DIR`.

---

## API Surface

Served by the FastAPI application in `app/server.py` (version `1.0.0-rc1`):

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe and health snapshot |
| `GET` | `/metrics` | Platform metrics and telemetry |
| `GET` | `/docs` | Interactive OpenAPI / Swagger documentation |
| `GET` | `/api/v1/agents` | List all registered agents |
| `GET` | `/api/v1/agents/{name}` | Get a single agent profile |
| `GET` | `/api/v1/tasks` | List task summaries |
| `POST` | `/api/v1/tasks/dispatch` | Dispatch a task for async execution |
| `GET` | `/api/v1/tasks/{task_id}` | Get task status and telemetry |
| `GET` | `/api/v1/tasks/{task_id}/status` | Task status detail |
| `GET` | `/api/v1/telemetry` | Runtime telemetry snapshot |
| `GET` | `/api/v1/diagnostics` | Readiness diagnostics |
| `POST` | `/api/v1/tools/issue` | Issue a scoped capability token |
| `POST` | `/api/v1/tools/execute` | Execute a tool with a validated token |
| `POST` | `/approvals/request` | Request a governance approval |
| `POST` | `/approvals/{id}/decide` | Approve or deny a pending approval |
| `POST` | `/api/v1/twin/session/start` | Start a Day-0 twin interview session |
| `POST` | `/api/v1/twin/session/{id}/answer` | Submit an interview answer |
| `POST` | `/api/v1/twin/session/{id}/commit` | Commit the interview as a profile (with consent) |
| `GET` | `/api/v1/twin/profile/{tenant_id}` | Get the latest committed twin profile |
| `POST` | `/api/v1/twin/events` | Ingest a work event and evolve the twin |
| `GET` | `/api/v1/twin/digest/{tenant_id}` | Get the weekly twin digest |
| `POST` | `/api/v1/twin/observe/git` | Observe a local git repo and feed commits to the twin |
| `POST` | `/api/v1/twin/actions/propose` | Propose twin actions from profile + digest |
| `POST` | `/api/v1/twin/actions/{action_id}/approve` | Approve a proposed action (human gate) |
| `POST` | `/api/v1/twin/actions/{action_id}/reject` | Reject a proposed action |
| `POST` | `/api/v1/twin/actions/{action_id}/execute` | Execute an approved action (records to SQLite/ledger only) |
| `GET` | `/api/v1/twin/actions/{tenant_id}` | List twin actions for a tenant |
| `GET` | `/api/v1/platform/status` | Honest platform status (version, agents, provider, persistence) |

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/aminazimi42-coder/aegis-agent.git
cd aegis-agent

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install the platform
pip install -e .

# Start the development server
uvicorn app.server:app --reload
```

Open the interactive API documentation at **http://127.0.0.1:8000/docs**.

### Dispatch a Task

```bash
curl -X POST http://127.0.0.1:8000/api/v1/tasks/dispatch \
  -H "Content-Type: application/json" \
  -d '{"task": "Plan the launch and validate the final outcome", "tenant_id": "default"}'
```

### Check Platform Status

```bash
curl http://127.0.0.1:8000/api/v1/platform/status
```

---

## Testing

```bash
./.venv/bin/python -m pytest -q
```

The test suite covers T01–T07 deliverables: platform integrity, LLM token substrate,
Day-0 cognitive twin, twin evolution, local git observer, proposed actions with approval gate,
and production integrity.

### Lint

```bash
./.venv/bin/python -m ruff check --fix .
./.venv/bin/python -m ruff check .
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Framework | FastAPI |
| Server | Uvicorn |
| Testing | pytest |
| Linting | ruff |
| Persistence | SQLite (`AEGIS_DATA_DIR`) |
| Default LLM | EchoProvider (offline) |

---

## Project Structure

```
aegis-agent/
├── agents/                     # Agent implementations
├── app/                        # FastAPI application layer
│   ├── server.py               # Application factory, middleware, routes
│   ├── api/routes.py           # Agent, task, telemetry, diagnostics routers
│   └── api/health.py           # Health and platform status
├── core/                       # Core platform modules
│   ├── ai_core.py              # Agent selection and workflow engine
│   ├── agent_registry.py       # Agent catalog (6 agents)
│   ├── llm_provider.py         # EchoProvider (default), HttpProvider
│   ├── persistence.py          # SQLite under AEGIS_DATA_DIR
│   ├── twin_interview.py       # Day-0 interview + consent
│   ├── twin_events.py          # Event ingest
│   ├── twin_evolution.py       # Deterministic evolve + weekly digest
│   ├── twin_git_observer.py    # Local git observer
│   ├── twin_actions.py         # Propose / approve / reject / execute
│   └── ...
├── tests/                      # Test suite (T01–T07)
├── docs/assets/                # SVG visual assets
├── pyproject.toml
├── setup.cfg
├── Dockerfile
└── README.md
```

---

## License & Credits

© Azimi Innovation Lab. See `LICENSE` for details.

**Azimi Innovation Lab · Amin Azimi · AI Architect**
