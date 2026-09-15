#!/usr/bin/env bash
# T183 — Submit-only notary helper.
#
# Sends the already-signed Aegis Operator.app to Apple Notary and prints
# a submission id.  Waiting for Apple's verdict and stapling the ticket
# are deliberately NOT in this slice; they remain locked for the next
# market pack.
#
# Without AEGIS_NOTARY_PROFILE the script prints NOTARY_PROFILE_MISSING
# and exits 0 so CI never fails on a machine without Apple credentials.
#
# This script does not open Safari.  It does not upload anywhere except
# notarytool submit when the profile is set.  The success word for a
# stapled ticket stays locked behind the next market slice.

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
  echo "APP_MISSING: no signed app found at dist/AegisOperator-mac/Aegis Operator.app"
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
# 1) Verify the signature — refuse if codesign verify fails.
# ------------------------------------------------------------------ #
if ! command -v codesign >/dev/null 2>&1; then
  echo "SIGNATURE_INVALID: codesign not available on this machine"
  exit 1
fi

if ! codesign --verify --deep --strict "$APP" >/dev/null 2>&1; then
  echo "SIGNATURE_INVALID: codesign verify --deep --strict failed on $APP"
  exit 1
fi

# ------------------------------------------------------------------ #
# 2) Build a zip next to the app with ditto.
# ------------------------------------------------------------------ #
ZIP="dist/AegisOperator-mac/Aegis Operator.notarize.zip"
mkdir -p "$(dirname "$ZIP")"
ditto -c -k --keepParent "$APP" "$ZIP"

# ------------------------------------------------------------------ #
# 3) Profile gate — without AEGIS_NOTARY_PROFILE, stop cleanly.
# ------------------------------------------------------------------ #
if [[ -z "${AEGIS_NOTARY_PROFILE:-}" ]]; then
  echo "NOTARY_PROFILE_MISSING"
  echo "To submit to Apple Notary, create a keychain profile on hermesdev:"
  echo "  xcrun notarytool store-credentials \"aegis-notary\" --apple-id \"aminazimi42@icloud.com\" --team-id \"3J54UZPZW3\""
  echo "  export AEGIS_NOTARY_PROFILE=aegis-notary"
  echo "  ./scripts/notarize_submit.sh"
  exit 0
fi

# ------------------------------------------------------------------ #
# 4) Submit with the keychain profile only.
#    No --apple-id, no --password, no --team-id, no raw key path.
#    Waiting and staple are the next market slice, not this one.
# ------------------------------------------------------------------ #
echo "NOTARY_SUBMIT: sending $ZIP to Apple Notary with profile $AEGIS_NOTARY_PROFILE"
SUBMIT_JSON=$(xcrun notarytool submit \
  "$ZIP" \
  --keychain-profile "$AEGIS_NOTARY_PROFILE" \
  --output-format json 2>&1 || true)

# Parse the submission id from JSON output.
SUBMISSION_ID=$(echo "$SUBMIT_JSON" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || true)

if [[ -n "$SUBMISSION_ID" ]]; then
  echo "NOTARY_SUBMITTED: $SUBMISSION_ID"
else
  echo "NOTARY_SUBMIT_FAILED: could not parse submission id from notarytool output"
  echo "$SUBMIT_JSON"
fi

exit 0
