# Aegis Agent — Privacy Model

Aegis is a **local-first operator twin** for a single senior operator.
This document is an honest statement of where data lives, what inference
runs by default, and what is explicitly **not** part of this core.

## Where data lives

- All durable state — profile, twin actions, jobs, feedback, and
  receipts — is written to **SQLite** under `AEGIS_DATA_DIR` on the
  operator's own machine (defaults to `data/`).
- Work products (briefs, memos, resumes, …) are local markdown files
  under the same `AEGIS_DATA_DIR`.
- There is no hosted multi-tenant database and no server-side tenant
  provisioning. The operator controls the directory and the files in it.

## Inference

- The default LLM provider is **EchoProvider** — a local, offline echo.
  No paid cloud LLM is wired by default.
- An optional **HttpProvider** adapter is available and is **off** unless
  the operator explicitly sets `AEGIS_LLM_PROVIDER=http` together with
  `AEGIS_LLM_BASE_URL` and `AEGIS_LLM_API_KEY`. When enabled, calls are
  still routed through the local `complete_safe` gate and
  `redact_secrets` before leaving the machine.

## Approvals

- Approving an action requires the **tenant id**, the **actor id**, and
  the **SHA-256 digest** of the action payload (`expected_payload_sha256`).
  Approvals are hash-bound; a mismatch is refused.
- The six specialists **propose only**. No specialist executes an action
  on its own. Execution happens only after a human approves.

## What is not in this core

- **No payment processor** in the twin core. There is no billing,
  card-charge, or license-key logic in this repository.
- **Grok Bot desktop teammates are a separate cloud product** — they are
  not part of this core and are not wired into the twin pipeline.
- This core does **not** claim end-to-end cloud encryption or a hosted
  multi-tenant SaaS deployment. There is no hosted multi-tenant billing
  or tenant-provisioning logic in this tree.

## Local durability

- `backup_tenant` / `restore_tenant` (`core/twin_backup.py`) round-trip a
  tenant's profile, actions, jobs, and receipt files through a local
  archive under `AEGIS_DATA_DIR`.
- A new `TwinInterviewStore` opened against the same `AEGIS_DATA_DIR`
  reads back the profile that was committed earlier — the SQLite file on
  disk is the single source of truth.
