<div align="center">

<img src="docs/assets/aegis-hero.svg" alt="Aegis Agent" width="100%"/>

# AEGIS AGENT

### FastAPI cognitive-twin platform with local work products and a human approve gate

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API%20Ready-009688)](https://fastapi.tianglia.com/)
[![License](https://img.shields.io/badge/License-Proprietary-purple)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-Passing-success)](https://github.com/)

</div>

---

## What This Is

Aegis Agent is a **FastAPI** application that maintains a per-tenant
**cognitive twin** — a local profile built from a Day-0 interview and evolved
by ingesting work events. The twin proposes actions that a **human must approve**
before anything executes. Work products (morning brief, meeting notes, resume,
board memo, etc.) are rendered as local markdown files under `AEGIS_DATA_DIR`.

The default LLM provider is **EchoProvider** — an offline echo that returns a
deterministic stub response. No paid LLM is wired in this revision. If
`AEGIS_LLM_PROVIDER` is not set, `get_provider()` returns `EchoProvider()`.

Persistence is **SQLite** stored under the `AEGIS_DATA_DIR` directory
(defaults to `data/`). On a free Render instance the service may cold-start
and lose in-memory state; SQLite files persist across requests only if the
volume is mounted.

There is no desktop UI in this tree — all interaction is via the FastAPI
server (`uvicorn`) or the `twin_cli.py` command-line tool.

---

## Quick Start

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install the platform
pip install -e .

# Run the test suite
./.venv/bin/python -m pytest -q

# Start the development server
uvicorn app.server:app --reload
```

Open interactive API docs at **http://127.0.0.1:8000/docs**.

---

## Twin CLI Commands

All commands are in `tools/twin_cli.py`. Each prints a JSON object to stdout
and exits 0 on success; `ValueError` / `PermissionError` prints
`{"error": str}` and exits 2.

```bash
python tools/twin_cli.py <command> [options]
```

| Command | Key flags | Description |
|---------|-----------|-------------|
| `status` | — | Print platform status |
| `interview-start` | `--tenant` | Start a Day-0 interview session |
| `interview-answer` | `--session --question --text` | Submit one interview answer |
| `interview-commit` | `--session --consent` | Commit the interview as a profile |
| `actions-propose` | `--tenant` | Propose twin actions from profile + digest |
| `actions-approve` | `--action-id` | Approve a proposed action (human gate) |
| `actions-execute` | `--action-id` | Execute an approved action |
| `render` | `--tenant` | Render weekly plan + review notes |
| `calendar-ics` | `--tenant --path` | Ingest a local `.ics` calendar file |
| `brief-morning` | `--tenant` | Render a one-page morning brief |
| `email-triage` | `--tenant --dir` | Triage a folder of `.eml` files |
| `brief-meetings` | `--tenant` | Render per-meeting briefs |
| `followups` | `--tenant` | Render the follow-up list |
| `delegate` | `--tenant` | Render the delegate pack |
| `decision-record` | `--tenant --title --decision --reason` | Record a yes/no decision |
| `decision-list` | `--tenant [--query]` | List recorded decisions |
| `style-lock` | `--tenant --dir` | Lock writing style from local text samples |
| `pr-review` | `--tenant --diff` | Turn a local diff into PR review notes |
| `expenses` | `--tenant --dir` | Ingest receipt `.txt` files into expense notes |
| `focus-block` | `--tenant --start [--duration] [--title]` | Create a focus-block hold |
| `travel` | `--tenant [--dir]` | Render a one-page travel pack |
| `team-inbox` | `--tenant --file` | Triage a team-chat export |
| `transcript-task` | `--tenant --file` | Turn a transcript `.txt` into a proposed action (audio-task sidecar supported) |
| `board-memo` | `--tenant` | Render a one-page board weekly memo |
| `resume` | `--tenant` | Render a one-page principal resume |
| `email-send` | `--tenant --action` | Send an approved email draft to local outbox |

---

## Twin API Routes (POST)

Served by the FastAPI application in `app/server.py` under the `/api/v1/twin`
prefix:

| POST route | Description |
|------------|-------------|
| `/api/v1/twin/session/start` | Start a Day-0 interview session |
| `/api/v1/twin/session/{session_id}/answer` | Submit an interview answer |
| `/api/v1/twin/session/{session_id}/commit` | Commit the interview as a profile |
| `/api/v1/twin/events` | Ingest a work event and evolve the twin |
| `/api/v1/twin/observe/git` | Observe a local git repo |
| `/api/v1/twin/observe/github` | Observe a GitHub repo via PAT |
| `/api/v1/twin/behavior/rebuild` | Rebuild the versioned behavioral snapshot |
| `/api/v1/twin/work-products/render` | Render local work-product files |
| `/api/v1/twin/calendar/ics` | Ingest a local `.ics` calendar file |
| `/api/v1/twin/brief/morning` | Render a one-page morning brief |
| `/api/v1/twin/email/triage` | Triage a folder of `.eml` files |
| `/api/v1/twin/brief/meetings` | Render per-meeting briefs |
| `/api/v1/twin/followups/render` | Render the follow-up list |
| `/api/v1/twin/delegate/render` | Render the delegate pack |
| `/api/v1/twin/decisions` | Record a yes/no decision |
| `/api/v1/twin/style/lock` | Lock writing style from local samples |
| `/api/v1/twin/pr/review` | Turn a local diff into PR review notes |
| `/api/v1/twin/expenses/ingest` | Ingest receipt `.txt` files |
| `/api/v1/twin/focus/block` | Create a focus-block hold |
| `/api/v1/twin/travel/render` | Render a travel pack |
| `/api/v1/twin/team/inbox` | Triage a team-chat export |
| `/api/v1/twin/transcript/task` | Turn a transcript into a proposed action |
| `/api/v1/twin/audio/task` | Turn an audio file + sidecar into a proposed task |
| `/api/v1/twin/memo/board` | Render a one-page board weekly memo |
| `/api/v1/twin/resume/render` | Render a one-page principal resume |
| `/api/v1/twin/email/send` | Send an approved email draft to local outbox |
| `/api/v1/twin/actions/propose` | Propose twin actions |
| `/api/v1/twin/actions/{action_id}/approve` | Approve a proposed action |
| `/api/v1/twin/actions/{action_id}/reject` | Reject a proposed action |
| `/api/v1/twin/actions/{action_id}/execute` | Execute an approved action |

Additional GET routes: `/api/v1/twin/profile/{tenant_id}`,
`/api/v1/twin/digest/{tenant_id}`, `/api/v1/twin/behavior/{tenant_id}`,
`/api/v1/twin/decisions/{tenant_id}`, `/api/v1/twin/actions/{tenant_id}`,
and `/api/v1/platform/status`.

---

## Testing

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python -m ruff check .
```

---

## Safety

The twin **proposes** actions; a human must **approve** before anything executes.
LLM completions go through `core/llm_safety.py`:

- **`complete_safe`** — calls the provider inside a tool allow-list cage
  (`ALLOWED_TOOLS`) and rejects responses that claim forbidden external
  actions ("payment sent", "email sent", etc.).
- **`redact_secrets`** — strips `AEGIS_LLM_API_KEY` and `AEGIS_GITHUB_TOKEN`
  values from the prompt before it reaches the provider.
- **`SecurityPolicy`** (`core/security.py`) — agent-name allow-list and
  `validate_task` SQL-injection guard used by the orchestrator.

These are local guards; they do not call any external service.

## Errors

Twin API routes return a unified 400 body on `ValueError`
(`core/api_errors.py`):

```json
{"detail": "<message>", "code": "TWIN_NO_PROFILE", "request_id": "<uuid4 hex>"}
```

`code` is a stable string from a known-message map (`TWIN_NO_PROFILE`,
`TWIN_ACTION_MISSING`, `TWIN_NOT_APPROVED`, …) or the fallback
`TWIN_ERROR`.  `detail` is `str(exc)` unchanged.

## CI

`.github/workflows/ci.yml` runs **ruff check** and **pytest -q** on
Python 3.11 for every push and pull request to `main`.

## Persistence Truth

State is **SQLite** under `AEGIS_DATA_DIR` (defaults to `data/`).
On a free Render instance the service may cold-start and lose in-memory
state; SQLite files persist only if the volume is mounted.  Do not assume
FinOps records or approval state survive a restart unless the volume is
persistent.  The default LLM is **EchoProvider** (offline echo); no paid
LLM and no live SMTP are wired in this revision.

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
| Default LLM | EchoProvider (offline, no paid LLM) |

---

## License

© Azimi Innovation Lab. See `LICENSE` for details.
