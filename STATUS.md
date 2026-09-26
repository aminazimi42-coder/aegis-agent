# Aegis Agent — Shipped Capability Status

Honest lock of what is actually shipped in this tree as of T70. See the **Now** and **Destination — Planned** sections in `README.md` for the current capability and the planned road ahead.

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

### Privacy and durability

- **Privacy and durability** — see [`docs/PRIVACY_MODEL.md`](docs/PRIVACY_MODEL.md).
  State is **SQLite** under `AEGIS_DATA_DIR` on the operator machine:
  local profile, actions, jobs, and receipts. Default inference is local
  **Echo**; the optional HTTP adapter is off unless configured. No
  Gmail, Slack, or SMTP is shipped. Six specialists: **Bita, Kian,
  Alina, Aylin, Ahmad, Amin**.

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

- **desktop_engine.py and .market are quarantined leftovers, not product** —
  `core/desktop_engine.py` and the `core/marketplace_sync.py` market directory
  (`.market`) are non-core scaffolds that remain in the tree for quarantine
  tests only; they are not wired into the product and do not call any external
  service.
- **Hosted multi-tenant SaaS** — there is no hosted multi-tenant billing,
  card-charging, or tenant-provisioning logic in this tree.
- **Installable desktop app** — unsigned installer folder `dist/AegisOperator-mac` exists; it is not notarized and not one-click.
- **Payment or license inside Aegis** — no Stripe, billing, or license-key
  logic ships in this repository.
- **Cloud LLM as the default** — the default provider is offline
  `EchoProvider`; no paid cloud LLM is wired by default.

## Optional

- **Default Echo; optional local adapter via `AGENT_LLM_BASE_URL`** — the default LLM provider is offline `EchoProvider`; an optional local OpenAI-compatible HTTP adapter activates when `AGENT_LLM_BASE_URL` is set (alongside `AEGIS_LLM_API_KEY` and `AEGIS_LLM_PROVIDER=http`), labeled in `complete_safe` as the `http` path. `AGENT_LLM_BACKEND=ollama` is an alias label that activates the same HTTP path; it is not a bundled binary and falls back to Echo when unreachable.
- **Buyer one-pager** — a local ``.md`` export built from the saved profile (name, role, goals, timezone) plus honest shipped facts; written under `AEGIS_DATA_DIR` or `~/.aegis/exports/`, never into the git worktree.
- **Operator start path** — `scripts/start_operator.sh` is the sole daily start path; it exports `AEGIS_DATA_DIR`, uses the project venv, and binds `127.0.0.1:8741`. The `desktop/macos/Aegis.app` bundle is a wrapper around it; it is not a notarized installer or a paid SKU.

## Layer 3

Layer 3 git slices T149–T152 landed; amin 2026-09-13 installer-path trial recorded (Install.command + venv + start_operator.sh + signed export); Aegis Operator.app not opened; installer is not one-click.

T153–T158 local commercialization pack landed; Apple-accepted notarize, live Stripe, and a real cloud license host remain locked.

T159–T162 local hardening pack landed: tool writes caged to `AEGIS_DATA_DIR`; propose cards show confidence (0–100) and a receipt-backed why line with a same-tenant conflict tag; status reports `duration_ms` and `http_token_cost` (zero on Echo); local entitlement file and signed brief export with path plus sha256 shipped; missing or expired entitlement returns Echo-limited; the secret-shape redactor covers bearer tokens and PEM private-key begin markers on propose body and audit/export text; HTTP adapter calls time out at 8 seconds and return Echo-limited typed English; the Echo-limited banner text includes the existing reason token (`missing_file` or `expired`).

T163 single-instance lock and status-on-page landed: `start_operator.sh` writes a lock file under `AEGIS_DATA_DIR` recording pid and port; a second start on the same port exits non-zero with the typed English error `port 8741 already in use`; a stale lock from a dead pid is replaced; the Home / Status panel shows `duration_ms` and `http_token_cost` from the platform status JSON; Echo keeps `http_token_cost` at zero.

T168 notary path landed: the codesign script submits to notarytool only when AEGIS_NOTARY_PROFILE is set; NOTARIZED prints only after stapler validate exits 0; without the profile it prints NOTARY_SKIPPED. Live Stripe and a real cloud license host remain locked — Planned, not shipped.

T169 remote status cannot unlock without local entitlement; Stripe and a deployed host remain locked.

T170 external checkout URL is optional and outside execute; live Stripe shop and deployed license host remain locked.

T171 notary submit path is wired; NOTARIZED prints only after stapler validate; live shop and stranger pack remain locked.

T172 stranger pack rebuilds with home copy and optional venv; live shop remains locked.

T173 local fulfill is grant-gated and outside execute; live Stripe shop remains locked.

T174 loop depth uses durable notes and profile; multi-month twin remains locked.

T175 receipt depth adds correlation id, note hash, digest preview, Intact/Tampered. Codesign paused.

T176 cages writes to AEGIS_DATA_DIR and extends redact. Codesign paused.

T177 honest start distinguishes missing vs expired and times out HTTP. Codesign paused.

T178 validates profile schema and writes a detached brief signature. Codesign paused. Four-slice depth pack closed.

T179 Stripe checkout sidecar outside execute; local issuer writes entitlement with source. Live Stripe shop remains locked.

T183 notary submit helper landed; staple and live billing remain locked.

T184 staple helper landed; live ticket still requires AEGIS_NOTARY_PROFILE on hermesdev; live billing locked.

T181 local issuer outside execute; live Apple ticket and live Stripe remain deferred.

T182 checkout sidecar stays outside execute; live Apple ticket and live Stripe shop remain deferred.

T185 documents live host aegis-agent-haka.onrender.com and instance 0.5c-512mb; free-tier cold-start sentence removed; LIMITATIONS + THREAT_NOTES added. T186 public demo denies raw PAT ingest; local loop unchanged.

T187 notarize_operator.sh wraps T183 submit + T184 staple; live Apple ticket still needs AEGIS_NOTARY_PROFILE on hermesdev; T188 billing locked.

T188 shop event handler stays outside execute; live Stripe keys and deployed webhook host remain outside git.

T189 page truth surfaces dry-run preview and Intact/Tampered verify-chain on the operator page. Instructions 2–4 not started.

T190 cages paths outside AEGIS_DATA_DIR, deepens redact with webhook/SSH shapes, and shows local brief+.sig verify on export. Instructions 3–4 not started.

T191 honest start preflight on start_operator.sh plus local-dead banner. Instruction 4 not started.

T192 optional reject reason and no silent Archive-to-Latest promote; four-slice pack closed.

T193 last reject reason on next propose and local session receipt under the data dir.

T194 operator Engine line for Echo / HTTP(Ollama alias) / Echo(fallback); no live key in git.

T195 optional SQLite encryption at rest; default plaintext; no passphrase in git.
T196 optional LLM token from Keychain on Darwin, mock on CI; no live key in git.
T197 encrypted inter-Mac portable bundle; mid-write kill and disk-full are typed fail. Four-slice pack T194–T197 closed.
T198 local evidence pack from existing chain/brief/audit/receipts; instructions 2–4 not started.
T199 weekly brief from durable profile proposes six cards; instructions 3–4 not started.
T200 page entitlement tier and quota-exhaust Echo; T201 observe-only local eml/ics propose; send is typed deny. Four-slice pack T198-T201 closed. No T202.
T202 page today-filter quota-remaining checklist must-not Approved digest Intact; T203 not started.
T203 weekly brief cites last approve and last reject; session id and last task restore after sleep; T204 not started.
T204 observe byte receipt; evidence zip includes last brief+.sig+Intact; T205 not started.
T205 Quit engine SIGTERM port 8741 only; start_operator.sh remains sole start; T206 not started.
T206 primary-specialist badge, caged path preview, copy-redact, why-drawer, Approved search; T207 not started.
T207 Quiet mode until next Start Session; Training vs Live work flag on propose; T208 not started.
T208 standing-order pin; tenant chip and typed switch; neighbor queues do not merge; T209 not started.
T209 desk-slip markdown under export; git observe-only status and last five subjects under AEGIS_DATA_DIR/work; eight-slice pack closed.
T209_FIX operator HTML JavaScript syntax in copy-redact onclick; both app.html copies parse; T210 not started.
T210 README Now records one-week morning-night cold-start local use; not two-week; not a behavioral twin.
T211 local tenant-bound decision ledger on approve/reject; neighbor isolated; Forget drops that tenant only.
T212 next propose cites last local tenant decisions within TTL; Forget clears hint; no auto-exec; not a multi-month twin.
T213 README Now proven owner one-week amin Ricardo separate days; not two-week; not a behavioral twin; no notarized.
T214 operator idle lock and Keychain PIN; lock blocks Propose/Approve/Reject/Export/Quit; neighbor not affected; no face/voice.
T215 optional Echo connect on operator page; Connect local engine sets AGENT_LLM_BASE_URL for this process; Use Echo returns Echo; fallback stays labeled; Ahmad propose card carries a must-not line; no seventh agent; no stripe in core.
T216 chain state Intact/Tampered on Approved cards; no Missing label; T217 not started.
T217 quiet notify sidecar label under Engine; T218 not started.
T218 caged inbox image to local signed PDF; T219 not started.
T219 today digest and standing-order pin; T220 not started.
T220 operator idle session lock AEGIS_SESSION_IDLE_SECONDS (default 900, min 60, max 86400); lockout after 5 wrong PINs for 5 minutes; Keychain service aegis-operator-session account {tenant_id}; forget_all drops lock material; no biometrics.
T221 optional Telegram sidecar after Approve only; Keychain service aegis-operator-telegram; AEGIS_TELEGRAM_BOT_TOKEN env optional; missing token → not_configured; network fail → TELEGRAM_SIDECAR_FAILED; execute/propose never import telegram; no claim Aegis is a messenger.
T222 optional local SMTP sidecar after Approve only; Keychain service aegis-operator-smtp; AEGIS_SMTP_PASSWORD env optional; missing config → not_configured; SMTP fail → SMTP_SIDECAR_FAILED; execute/propose never import smtp; T201 observe send-deny unchanged; no claim Aegis is an email client.
T223 optional local HTTP engine connect button reuses AGENT_LLM_BASE_URL / Ollama alias; Echo default; dead URL → Echo (fallback); disconnect returns Echo; token via T196 Keychain/mock; no cloud key in git; execute/propose never import a new provider; no stripe in core.
T224 caged inbox image to tenant-scoped local signed PDF; source under AEGIS_DATA_DIR/{tenant}/…; png/jpg/jpeg/webp only; export under {tenant}/export/inbox_{utc}.pdf + .sig; typed OUTSIDE_CAGE/MISSING/UNSUPPORTED; neighbor cannot read; forget drops tenant export; no cloud OCR; no stripe in core.
T225 session evidence zip under AEGIS_DATA_DIR/{tenant}/export/session_evidence_{utc}.zip; zip contains last signed brief+.sig, last receipt digest, verify-chain result; Intact/Tampered on the Approved card after Approve in the same turn; neighbor tenant zip is empty or 404; forget drops that tenant export zip; no stripe in core.
T226 optional Touch ID after PIN, mock in CI; Darwin path via LocalAuthentication (LAContext) labeled optional; CI/Linux mock returns mock_ok / mock_cancel / mock_unavailable as typed strings; failed or cancelled biometrics returns to PIN; no silent unlock; Touch ID unlocks session lock only, does not execute; Approve still required; no face/voice capture or onboarding in core; both app.html copies byte-sync; no stripe in core.
T227 stranger Mac install without Terminal; double-click Install.command or Aegis Operator.app in dist/AegisOperator-mac; data stays in $HOME/.aegis on port 8741; missing python3.11 prints official 3.11.9 macos11.pkg URL from python.org and exits 1, does not auto-download; no Safari launch; no repo/git/Hermes/VS Code on the stranger account; pack does not copy builder .aegis PII; README Now names double-click path; both app.html copies byte-sync; no stripe in core.
