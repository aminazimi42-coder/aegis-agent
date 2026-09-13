#!/usr/bin/env bash
# T158/T167/T167_CONTINUE/T168_CONTINUE — Codesign the Aegis Operator.app
# only when a Developer ID Application identity exists in the keychain.
#
# If no Developer ID identity is found the script prints UNSIGNED and exits 0
# — the Mac folder stays unsigned and is not store-distributed software.
#
# If an identity exists, codesign --force --deep --options runtime --timestamp
# --sign "$IDENTITY" is run on the app.  The first Developer ID Application
# identity found is used, or AEGIS_CODESIGN_IDENTITY if that env is set and
# non-empty.
#
# After signing, codesign --verify --deep --strict is run on the app.  The
# script prints SIGNED: <identity> only if verify exits 0.
#
# After verify succeeds, if AEGIS_NOTARY_PROFILE is unset or empty the script
# prints NOTARY_SKIPPED and exits 0.  When AEGIS_NOTARY_PROFILE is set, the
# script submits to notarytool with that keychain profile only — no Apple ID
# or password flags are passed.  After submit the script waits for the notary
# status.  stapler staple runs only when Apple reports Accepted.  The script
# prints NOTARIZED only if stapler validate on the app exits 0; otherwise it
# prints NOTARY_PENDING or NOTARY_FAILED and exits 0.
#
# NOTARY_LOCKED_UNTIL_TICKET — a staple ticket is still required for the
# NOTARIZED print; without it the shipped tree is not claimed as Apple-accepted.
#
# This script does not open Safari.  It does not upload anywhere except
# notarytool when the profile is set.  Never writes the word notarized as a
# success state unless stapler validate would pass.

set -euo pipefail

# ------------------------------------------------------------------ #
# 0) App path — positional arg, env override, or default.
# ------------------------------------------------------------------ #
APP="${1:-${AEGIS_CODESIGN_APP:-}}"
if [[ -z "$APP" ]]; then
  DEFAULT="dist/AegisOperator-mac/Aegis Operator.app"
  if [[ -d "$DEFAULT" ]]; then
    APP="$DEFAULT"
  fi
fi

if [[ -z "$APP" || ! -d "$APP" ]]; then
  echo "APP_MISSING: no app path to sign; the Mac folder stays unsigned"
  exit 0
fi

# ------------------------------------------------------------------ #
# 1) Is codesign available?
# ------------------------------------------------------------------ #
if ! command -v codesign >/dev/null 2>&1; then
  echo "UNSIGNED: no codesign on this machine; the Mac folder stays unsigned"
  exit 0
fi

# ------------------------------------------------------------------ #
# 2) Is a Developer ID Application identity in the keychain?
# ------------------------------------------------------------------ #
IDENTITY=""

# Honor AEGIS_CODESIGN_IDENTITY if set and non-empty.
if [[ -n "${AEGIS_CODESIGN_IDENTITY:-}" ]]; then
  IDENTITY="$AEGIS_CODESIGN_IDENTITY"
elif command -v security >/dev/null 2>&1; then
  IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null \
    | grep -m 1 'Developer ID Application' \
    | sed -E 's/.*"(.*)".*/\1/' || true)"
fi

if [[ -z "$IDENTITY" ]]; then
  echo "UNSIGNED: no Developer ID identity; the Mac folder stays unsigned"
  exit 0
fi

# ------------------------------------------------------------------ #
# 3) Codesign the app with a timestamp.
# ------------------------------------------------------------------ #
echo "SIGNING: $APP with identity: $IDENTITY"
codesign --force --deep --options runtime --sign "$IDENTITY" --timestamp "$APP"

# ------------------------------------------------------------------ #
# 4) Verify the signature — print SIGNED only if verify exits 0.
# ------------------------------------------------------------------ #
if codesign --verify --deep --strict "$APP" >/dev/null 2>&1; then
  echo "SIGNED: $IDENTITY"
else
  echo "UNSIGNED: codesign verify failed; the Mac folder stays unsigned"
  exit 0
fi

# ------------------------------------------------------------------ #
# 5) Notary — only when AEGIS_NOTARY_PROFILE is set and non-empty.
#    Without a profile the script prints NOTARY_SKIPPED and exits 0.
#    With a profile it submits to notarytool, waits for status, and
#    runs stapler staple + validate.  NOTARIZED prints only after
#    stapler validate exits 0.
# ------------------------------------------------------------------ #
if [[ -z "${AEGIS_NOTARY_PROFILE:-}" ]]; then
  echo "NOTARY_SKIPPED"
  exit 0
fi

# Submit with the keychain profile only — no Apple ID or password flags.
echo "NOTARY_SUBMIT: submitting $APP with profile $AEGIS_NOTARY_PROFILE"
SUBMIT_OUTPUT=$(notarytool submit \
  --keychain-profile "$AEGIS_NOTARY_PROFILE" \
  "$APP" 2>&1 || true)
SUBMISSION_ID=$(echo "$SUBMIT_OUTPUT" \
  | grep -i 'id:' | head -1 \
  | sed -E 's/.*id:[[:space:]]*([a-zA-Z0-9-]+).*/\1/' || true)

if [[ -z "$SUBMISSION_ID" ]]; then
  echo "NOTARY_FAILED: could not parse submission id from notarytool"
  exit 0
fi

# Wait for the notary status to resolve.
echo "NOTARY_WAIT: waiting for submission $SUBMISSION_ID"
WAIT_OUTPUT=$(notarytool wait "$SUBMISSION_ID" \
  --keychain-profile "$AEGIS_NOTARY_PROFILE" 2>&1 || true)
STATUS_LINE=$(echo "$WAIT_OUTPUT" | grep -i 'status:' | tail -1 || true)

if echo "$STATUS_LINE" | grep -qi 'Accepted'; then
  # Staple the ticket to the app.
  if stapler staple "$APP" 2>/dev/null; then
    if stapler validate "$APP" >/dev/null 2>&1; then
      echo "NOTARIZED"
    else
      echo "NOTARY_FAILED: stapler validate did not pass"
    fi
  else
    echo "NOTARY_FAILED: stapler staple did not succeed"
  fi
elif echo "$STATUS_LINE" | grep -qi 'In Progress'; then
  echo "NOTARY_PENDING"
else
  echo "NOTARY_FAILED: notary status was not accepted"
fi

exit 0
