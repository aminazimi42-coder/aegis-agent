# Aegis Agent — Limitations

User-facing limitations of this platform as of T185.

## Engine

- **Echo is the default engine.** No cloud LLM is called unless the operator explicitly sets an HTTP adapter (`AEGIS_LLM_PROVIDER=http` with a base URL and key). Without that, every completion is a local echo.

## Render is a demo

- **The Render host is a demo, not the product.** The live demo at `https://aegis-agent-haka.onrender.com` runs on a `0.5c-512mb` instance. Local data lives under `$HOME/.aegis` on the operator machine, not on the Render disk — SQLite state on Render persists only if a volume is mounted.

## No live card charge

- **No live card charge exists in core.** The entitlement is a local signed file. When the file is missing, expired, or mutated, the platform returns Echo-limited. No card form, no Stripe secret, no checkout URL is deployed in core.

## Codesign and notarize

- **Codesign may exist on the operator machine, but notarize/staple is not a shipped claim.** The scripts gate on `AEGIS_NOTARY_PROFILE` and print `NOTARY_SKIPPED` without it. The success word prints only after `stapler validate` passes on that machine — it is not a blanket shipped claim.

## Six specialists propose only

- **Six specialists propose only; a human must approve.** Alina, Kian, Bita, Aylin, Ahmad, and Amin can propose actions, but nothing executes without a human approval gate.
