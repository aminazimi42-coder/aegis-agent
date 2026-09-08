# T127 — Local Truth Audit

A sentence-by-sentence audit of every product, deployment, and capability
claim in STATUS.md, RELEASES.md, and README.md against the running code on
main at commit ab0e1e0 (725 passed, 1 skipped). No new endpoints, no new
agents, no UI redesign — only stale sentences were fixed.

## 1. Six specialists propose only

The specialist catalog registers exactly six agents: Alina (strategic
coordination), Kian (operational execution), Bita (analysis and synthesis),
Aylin (quality and validation), Ahmad (security and oversight), and Amin
(finance and executive bridge). Each one proposes actions only; no
specialist executes on its own. The `insert_specialist_proposal` function
writes a proposal row, and execution requires a separate human approval
through `actions_approve`. This claim is true in the running code and in
all three documents.

## 2. Digest bind

Every action approval is hash-bound. The `TwinActionApproveRequest`
model requires `expected_payload_sha256`, and the approve endpoint
compares that digest to the canonical SHA-256 of the stored payload. A
mismatch is refused. The README pipeline diagram and STATUS.md both state
this correctly.

## 3. Tenant bind

Proposed, approved, and executed actions are scoped to `tenant_id`. A
cross-tenant approve or execute is refused. The `tenant_id` column is
present on every action row and every query filters by it. STATUS.md and
RELEASES.md both state this accurately.

## 4. Echo default

`get_provider()` in `core/llm_provider.py` returns `EchoProvider()` when
`AEGIS_LLM_PROVIDER` is unset or not `http`. The `complete_safe` gateway
is labeled `echo` by default and `http` only when the HTTP adapter is
configured. No paid LLM is wired by default. This is correctly stated in
all three documents.

## 5. No PSP in core

There is no payment service provider, billing, card-charge, or
license-key logic anywhere in `core/`. The quarantined scaffolds in
`core/desktop_engine.py` and `core/marketplace_sync.py` raise
`RuntimeError("quarantined")` and call no external service. STATUS.md
"Not shipped" section and README "Not shipped" column both state this
truthfully.

## 6. Local SQLite

All durable state — profile, actions, jobs, feedback, receipts — is
persisted to SQLite files under `AEGIS_DATA_DIR` (defaults to `data/`).
The `backup_tenant` and `restore_tenant` functions round-trip a tenant's
state through a local archive under the same root. There is no hosted
multi-tenant database. This is accurately stated in STATUS.md,
RELEASES.md, and README.md.

## 7. Two-column home

The operator home page renders a two-column layout: the pending-action
queue on one side and the approved/rejected/due panels on the other.
`core/twin_home.py` pulls pending actions through `prioritize_pending`
and renders them alongside the status panels. The desktop `app.html`
template implements the two-column layout. This was shipped in T120 and
is not contradicted by any existing document.

## 8. Offline banner

The operator page shows an "Engine offline" banner when the local twin
is not reachable and points back to `scripts/run_local.sh`. The
`offline_mode()` function in `core/twin_local_view.py` returns True when
no HTTP provider is configured, and the desktop `app.html` renders the
banner conditionally. STATUS.md mentions this in the "Optional" section
and is accurate.

## 9. Redact

`core/redact.py` provides regex-based redaction of secret-shaped
substrings (API keys, bearer tokens, `AEGIS_LLM_API_KEY`,
`AEGIS_GITHUB_TOKEN`) in proposed card text and payloads. The
`redact_payload` function walks dict/list/str values so a full payload
can be redacted in one call. The `t92_untrusted_ingest` module prefilters
untrusted input through `redact` before proposing. This was shipped in
T124 and is not contradicted by any existing document.

## 10. Receipt chain

Every execution writes a local markdown receipt under
`receipts/{action_id}.md`. Each receipt is hash-chained to the previous
receipt for the same tenant — the chain includes the prior receipt's
SHA-256 in the current receipt's header. A dry-run mode is available that
renders the receipt without executing or writing the outbox file. This
was shipped in T125 and is not contradicted by any existing document.

## 11. Neighbor purge

The `purge_tenant` function removes all twin stores for a tenant
(profile, actions, jobs, receipts) but only after verifying that no
neighboring tenant's receipts reference the purged tenant's actions.
A typed confirm string is required. Receipt files for surviving tenants
are preserved. This was shipped in T126 and is not contradicted by any
existing document.

## 12. Signed export

`signed_export` in `core/twin_local_recall.py` writes a SHA-256-signed
export file under `AEGIS_DATA_DIR/export/`. The export includes the
tenant's actions and a signature line that can be verified later. This
was shipped in T126 and is not contradicted by any existing document.

## 13. Conflict tag

When a new propose shares the same title or payload SHA-256 as an
existing pending action, the `conflict` column is set to `1` on the new
row. When a second `insert_specialist_proposal` writes to the same
`action_id`, the duplicate is tagged `conflict=True` and the first
payload is never clobbered. This was shipped in T99/T126 and is not
contradicted by any existing document.

## 14. No production-SaaS claim

None of the three documents claim a hosted multi-tenant SaaS, billing,
or card-charging product. STATUS.md "Not shipped" explicitly states
"there is no hosted multi-tenant billing, card-charging, or
tenant-provisioning logic in this tree." README "Not shipped" column
lists "Hosted multi-tenant SaaS / billing / card-charging." This is
true.

## 15. Render is demo not the product

The `render.yaml` and `Dockerfile` exist for local-first hosting on a
free Render instance as a demo, not as the product. The product is the
local-first cognitive twin running on the operator's machine via
`scripts/run_local.sh`. README.md correctly notes that a free Render
instance may cold-start and lose in-memory state. RELEASES.md mentions
Render and Docker as deployment configuration, which is accurate — they
are deployment manifests, not the product itself.

## 16. Grok Bot is not Aegis

`docs/PRIVACY_MODEL.md` states that "Grok Bot desktop teammates are a
separate cloud product — they are not part of this core and are not
wired into the twin pipeline." No Grok Bot integration exists in the
codebase. This is true and not contradicted by STATUS.md, RELEASES.md,
or README.md.

## 17. Desktop still needs run_local.sh

The desktop `app.html` template is a local web UI, not a packaged
desktop binary or installer. It requires the local engine to be running
via `scripts/run_local.sh`. There is no standalone `.app` product without
the engine. STATUS.md "Optional" section states this correctly.

## 18. Ahmad and Amin are gates not executors

Ahmad (security and oversight) and Amin (finance and executive bridge)
are specialists that propose only, like the other four. Neither
executes actions autonomously. All six specialists write proposal rows;
execution requires a human approval through the approve endpoint. This
is correctly stated in all three documents.

## 19. Version string consistency

The version string `1.0.0-rc1` is consistent across `pyproject.toml`,
`core/config.py`, `app/health.py`, `app/release.py`, `app/server.py`,
`docs/manifests/deployment-manifest.yaml`, and `docs/manifests/
system-manifest.yaml`. The `setup.cfg` file carries `0.1.0` — a legacy
packaging stub that predates the rc1 versioning and is not consumed by
the running application. The Helm chart `Chart.yaml` uses
`appVersion: "1.0.0"` which is the chart app version, a separate
packaging concern from the application version. README.md and
RELEASES.md both state `1.0.0-rc1`, matching the running code.

## 20. Open test count

The current regression suite runs 725 passed, 1 skipped, 0 failed. The
RELEASES.md verification section previously stated "588 passed, 1
skipped" — a stale count from an earlier release. It has been updated
to "725 passed, 1 skipped" to match the running suite at commit
ab0e1e0.
