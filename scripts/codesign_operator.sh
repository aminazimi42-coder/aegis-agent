#!/usr/bin/env bash
# T158/T167/T168 — Codesign the Aegis Operator.app only when a Developer ID
# Application identity exists in the keychain.
#
# If no Developer ID identity is found the script prints UNSIGNED and exits 0
# — the Mac folder stays unsigned and is not store software.
#
# If an identity exists, codesign --force --deep --options runtime --timestamp
# --sign "$IDENTITY" is run on the app.  The first Developer ID Application
# identity found is used, or AEGIS_CODESIGN_IDENTITY if that env is set and
# non-empty.
#
# After a successful codesign:
# - If AEGIS_NOTARY_PROFILE is unset or empty: print NOTARY_SKIPPED, exit 0.
# - If AEGIS_NOTARY_PROFILE is set: submit to notarytool using that keychain
#   profile.  After submit, wait/check status.  When Apple reports Accepted,
#   run stapler staple on the app.  Print NOTARIZED only if
#   `stapler validate` on the app exits 0.  Otherwise print NOTARY_PENDING
#   or NOTARY_FAILED and exit 0 — the dry operator path never fails the
#   script just because this machine has no ticket.
#
# This script does not open Safari and does not upload anywhere except
# notarytool when the profile is set.

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
# 4) Notary submission — only when AEGIS_NOTARY_PROFILE is set and
#    non-empty.  Otherwise skip.
# ------------------------------------------------------------------ #
NOTARY_PROFILE="${AEGIS_NOTARY_PROFILE:-}"

if [[ -z "$NOTARY_PROFILE" ]]; then
  echo "NOTARY_SKIPPED"
  exit 0
fi

# ------------------------------------------------------------------ #
# 5) Submit to notarytool using the keychain profile.
# ------------------------------------------------------------------ #
if ! command -v notarytool >/dev/null 2>&1; then
  echo "NOTARY_SKIPPED: notarytool not available"
  exit 0
fi

echo "NOTARY_SUBMIT: profile=$NOTARY_PROFILE"
SUBMIT_OUTPUT="$(notarytool submit "$APP" \
  --keychain-profile "$NOTARY_PROFILE" \
  --wait 2>&1 || true)"

# ------------------------------------------------------------------ #
# 6) Check the notarytool status from the submit output.
# ------------------------------------------------------------------ #
if echo "$SUBMIT_OUTPUT" | grep -qi "Accepted"; then
  # ------------------------------------------------------------------ #
  # 7) Staple the ticket to the app.
  # ------------------------------------------------------------------ #
  stapler staple "$APP" 2>/dev/null || true

  # ------------------------------------------------------------------ #
  # 8) Validate the staple — only print NOTARIZED if this succeeds.
  # ------------------------------------------------------------------ #
  if stapler validate "$APP" >/dev/null 2>&1; then
    echo "NOTARIZED"
    exit 0
  else
    echo "NOTARY_PENDING: stapler validate did not succeed"
    exit 0
  fi
elif echo "$SUBMIT_OUTPUT" | grep -qi "Rejected"; then
  echo "NOTARY_FAILED: Apple rejected the submission"
  exit 0
else
  echo "NOTARY_PENDING: submission not yet accepted"
  exit 0
fi
