# Aegis Agent — Shipped Capability Status

Honest lock of what is actually shipped in this tree as of T53.

## Shipped

- **EchoProvider** is the default LLM provider (`core/llm_provider.py`).
  `get_provider()` returns `EchoProvider()` when `AEGIS_LLM_PROVIDER` is unset
  or not `http`.
- **`complete_safe`** (`core/llm_safety.py`) wraps every LLM completion in a
  tool allow-list cage and rejects responses that claim forbidden external
  actions.
- **SQLite persistence** for approvals, budgets, and jobs under
  `AEGIS_DATA_DIR` (defaults to `data/`).
- **Scheduler tick** (`core/twin_scheduler.py`) does **not** send mail.
- **Goal plan** (`core/twin_goal_plan.py`) **proposes only** — nothing
  executes without human approval.
- **Risk levels L0–L3** (`core/twin_risk.py`).
- **Memory show / forget** (`core/twin_memory_control.py`).
- **`home.md`** rendered by `core/twin_home.py` (`render_home`).
- **Style lock** applied on brief and home renders
  (`core/twin_style_lock.py`).
- **Resume** renders the principal name (`core/twin_resume_pack.py`).
- **Outbox payload** includes a `body` field (`core/twin_email_send.py`).
- **Golden busy-day test** covers the propose → approve → outbox flow
  (`tests/test_t52_busy_day_brief.py`).
- **Execute after approve** writes a local outbox file or `executed.md`
  (`core/twin_actions.py`).
- **CI on push** (`.github/workflows/ci.yml`) runs `ruff check` and
  `pytest -q` on Python 3.11.

## Not shipped

- **Installable desktop app** — there is no packaged desktop binary or
  installer in this tree.
- **Payment or license inside Aegis** — no Stripe, billing, or license-key
  logic ships in this repository.
- **Cloud LLM as the default** — the default provider is offline
  `EchoProvider`; no paid cloud LLM is wired by default.

## Optional

- **HTTP provider** (`HttpProvider`) activates only when both
  `AEGIS_LLM_BASE_URL` and `AEGIS_LLM_API_KEY` environment variables are set
  and `AEGIS_LLM_PROVIDER=http`.
