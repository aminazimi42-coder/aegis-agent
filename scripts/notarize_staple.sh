#!/usr/bin/env bash
# T184 — Staple-only helper.
#
# Checks an existing notary submission and staples the signed app only
# when Apple reports Accepted.  Without a profile, without a submission
# id, or before Accepted: prints NOTARY_PENDING or NOTARY_PROFILE_MISSING
# and never prints NOTARIZED.
#
# This script does not open Safari.  It does not submit a new zip —
# submission stays in T183.  It does not pass --apple-id, --password,
# or a raw key path to notarytool info.

set -euo pipefail

# ------------------------------------------------------------------ #
# 0) App path — env override or default.
# ------------------------------------------------------------------ #
APP="${AEGIS_NOTARY_APP:-}"
if [[ -z "$APP" ]]; then
  DEFAULT="dist/AegisOperator-mac/Aegis Operator.app"
  if [[ -d "$DEFAULT" ]]; then
    APP="$DEFAULT"
  fi
fi

if [[ -z "$APP" || ! -d "$APP" ]]; then
  echo "NO_APP: no signed app found at dist/AegisOperator-mac/Aegis Operator.app"
  echo "Set AEGIS_NOTARY_APP to the path of a .app directory if it lives elsewhere."
  exit 1
fi

# AEGIS_NOTARY_APP, if set, must end in .app and be a directory.
if [[ -n "${AEGIS_NOTARY_APP:-}" ]]; then
  case "$APP" in
    *.app) ;;
    *) echo "APP_INVALID: AEGIS_NOTARY_APP must point to a .app directory"; exit 1 ;;
  esac
fi

# ------------------------------------------------------------------ #
# 1) Profile gate — without AEGIS_NOTARY_PROFILE, stop cleanly.
# ------------------------------------------------------------------ #
if [[ -z "${AEGIS_NOTARY_PROFILE:-}" ]]; then
  echo "NOTARY_PROFILE_MISSING"
  echo "To submit and staple, create a keychain profile on hermesdev:"
  echo "  xcrun notarytool store-credentials \"aegis-notary\" --apple-id \"aminazimi42@icloud.com\" --team-id \"3J54UZPZW3\""
  echo "  export AEGIS_NOTARY_PROFILE=aegis-notary"
  echo "  ./scripts/notarize_staple.sh"
  exit 0
fi

# ------------------------------------------------------------------ #
# 2) Submission id — from env only; do not invent one.
# ------------------------------------------------------------------ #
ID="${AEGIS_NOTARY_SUBMISSION_ID:-}"
if [[ -z "$ID" ]]; then
  echo "NOTARY_PENDING no_submission_id"
  echo "Export AEGIS_NOTARY_SUBMISSION_ID with the id from notarize_submit.sh"
  exit 0
fi

# ------------------------------------------------------------------ #
# 3) Status check only — keychain-profile, no --apple-id/--password.
# ------------------------------------------------------------------ #
INFO_JSON=$(xcrun notarytool info "$ID" \
  --keychain-profile "$AEGIS_NOTARY_PROFILE" \
  --output-format json 2>&1 || true)

STATUS=$(echo "$INFO_JSON" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)

if [[ -z "$STATUS" ]]; then
  echo "NOTARY_PENDING could_not_parse_status"
  echo "$INFO_JSON"
  exit 0
fi

if [[ "$STATUS" != "Accepted" ]]; then
  echo "NOTARY_PENDING $STATUS"
  exit 0
fi

# ------------------------------------------------------------------ #
# 4) Accepted — staple the ticket, then validate.
# ------------------------------------------------------------------ #
xcrun stapler staple "$APP" 2>&1 || true

if xcrun stapler validate "$APP" >/dev/null 2>&1; then
  echo "NOTARIZED"
else
  echo "NOTARY_FAILED"
  echo "stapler validate did not exit 0 on $APP"
fi

exit 0
