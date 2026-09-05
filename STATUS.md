# Aegis Agent — Shipped Capability Status

Honest lock of what is actually shipped in this tree as of T70.

## Shipped

### Specialist agents

- **Six agents** registered in the specialist catalog:
  **Alina** (strategic coordination), **Kian** (operational execution),
  **Bita** (analysis and synthesis), **Aylin** (quality and validation),
  **Ahmad** (security and oversight), **Amin** (finance and executive bridge).
- **EchoProvider** is the default LLM provider (`core/llm_provider.py`).
  `get_provider()` returns `EchoProvider()` when `AEGIS_LLM_PROVIDER` is unset
  or not `http`. No paid LLM is wired by default.
- **`complete_safe`** (`core/llm_safety.py`) is the single LLM completion
  gateway; it wraps every call in a tool allow-list cage and rejects
  responses that claim forbidden external actions ("payment sent",
  "email sent", …).

### Cognitive twin

- **Consented profile** — a Day-0 interview evolves the twin from a tenant
  profile (`core/twin_interview.py`).
- **Hash-bound approve** — approvals are bound to the canonical envelope
  SHA-256 digest of the action payload (`core/twin_actions.py`,
  `TwinActionApproveRequest.expected_payload_sha256`).
- **Tenant bind** — proposed, approved, and executed actions are scoped to
  `tenant_id`; cross-tenant use is refused (`core/twin_actions.py`).
- **Home queue** from `twin_actions` — the executive home page renders the
  pending-action queue from the twin action store (`core/twin_home.py`).
- **Execute after receipt** — approved actions write a local outbox file or
  `receipts/{action_id}.md` on execution; nothing sends externally
  (`core/twin_actions.py`).
- **`forget_all`** and **typed `purge_tenant`** — memory control drops one
  field (`forget`) or purges all twin stores with a typed confirm string
  (`core/twin_memory_control.py`).
- **L0 allow-list** — risk classification L0 only for effects on
  `ALLOWED_L0_EFFECTS`; an unknown effect is at least L1
  (`core/twin_risk.py`, T63).
- **Why-replay** — the `why` column on actions survives a process restart
  (`core/twin_actions.py`, T64).
- **Feedback rows** — approve/reject writes a feedback row labeled
  `complete_safe` with the actor and timestamp (`core/twin_actions.py`,
  T65).
- **Labeled `complete_safe`** — the single gateway is labeled with the
  provider kind (`echo` by default, `http` when configured) (T66).

### Scheduler and persistence

- **UTC scheduler** — `due_at` is normalized to UTC; the scheduler tick
  marks due jobs but sends no mail (`core/twin_scheduler.py`, T68).
- **Local SQLite backup/restore** — `backup_tenant` and `restore_tenant`
  round-trip a tenant's profile, actions, jobs, and decisions through a
  local file under `AEGIS_DATA_DIR` (`core/twin_backup.py`, T69).
- **SQLite persistence** for approvals, budgets, jobs, and receipts under
  `AEGIS_DATA_DIR` (defaults to `data/`).

### Work products

- **Morning brief**, **meeting briefs**, **followups**, **delegate pack**,
  **board memo**, **resume**, **travel pack**, **focus block**, **decision
  record**, **style lock**, **PR review**, **expenses**, **team inbox**,
  **transcript task**, **audio task**, **email triage**, **email send to
  local outbox** — all render local markdown files under `AEGIS_DATA_DIR`.

### Other

- **CI on push** (`.github/workflows/ci.yml`) runs `ruff check` and
  `pytest -q` on Python 3.11.
- **Quarantined scaffolds** — non-core product scaffolds (Slack, Email,
  Omnichannel bridges) raise `RuntimeError("quarantined")`; they are not
  wired and do not call any external service (`core/omnichannel.py`, T67).

## Not shipped

- **Hosted multi-tenant SaaS** — there is no hosted multi-tenant billing,
  card-charging, or tenant-provisioning logic in this tree.
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
