# Aegis Agent — Threat Notes

Short threat notes for this platform as of T185.

## Untrusted ingest

- **Untrusted ingest (email text, transcript, task string) is prefilter + redact, not a trusted prompt.** Ingested content is never treated as a trusted system instruction; it passes through the local allow-list cage (`complete_safe`) and the secret-shape redactor before any processing.

## Public demo is not a private twin

- **The public demo must not be treated as a private twin.** The Render host at `https://aegis-agent-haka.onrender.com` is a public demo; the operator's private twin data lives under `$HOME/.aegis` on the local machine, not on the demo host.

## GitHub PAT

- **A GitHub PAT must not be pasted into a public URL.** The GitHub observer reads the token from the environment (`AEGIS_GITHUB_TOKEN`) or a local file; it is never embedded in a URL, logged, or committed.

## Approval binds to digest

- **Approval binds to the canonical SHA-256 digest of the action payload.** A mutated payload cannot execute (T56) — the digest mismatch rejects the action before any external effect.
