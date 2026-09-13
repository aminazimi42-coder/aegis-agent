#!/usr/bin/env bash
# T158 — Codesign the Aegis Operator.app only when a Developer ID identity exists.
#
# If no codesign or no Developer ID Application identity is found, the script
# prints UNSIGNED and exits 0 — the Mac folder stays unsigned and is not
# App Store software.
#
# If an identity exists, codesign --force --deep --options runtime is run.
# Notary submission happens only when AEGIS_NOTARY_PROFILE is set; otherwise
# the script prints NOTARY_SKIPPED and exits 0.
#
# This script never claims the app is notarized unless stapler validate would
# pass.  It does not open Safari and does not upload the app except to
# notarytool when the profile is set.

set -euo pipefail

APP="${1:-}"
if [[ -z "$APP" ]]; then
  DEFAULT="dist/AegisOperator-mac/Aegis Operator.app"
  if [[ -d "$DEFAULT" ]]; then
    APP="$DEFAULT"
  fi
fi

# ------------------------------------------------------------------ #
# 1) Is codesign available?
# ------------------------------------------------------------------ #
if ! command -v codesign >/dev/null 2>&1; then
  echo "UNSIGNED: no codesign on this machine; the Mac folder stays unsigned and is not App Store software"
  exit 0
fi

# ------------------------------------------------------------------ #
# 2) Is a Developer ID Application identity in the keychain?
# ------------------------------------------------------------------ #
IDENTITY=""
if command -v security >/dev/null 2>&1; then
  IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null \
    | grep -m 1 'Developer ID Application' \
    | sed -E 's/.*"(.*)".*/\1/' || true)"
fi

if [[ -z "$IDENTITY" ]]; then
  echo "UNSIGNED: no Developer ID identity; the Mac folder stays unsigned and is not App Store software"
  exit 0
fi

# ------------------------------------------------------------------ #
# 3) Codesign the app if the path exists
# ------------------------------------------------------------------ #
if [[ -z "$APP" || ! -d "$APP" ]]; then
  echo "UNSIGNED: no Developer ID identity; no app path to sign"
  exit 0
fi

echo "SIGNING: $APP with identity: $IDENTITY"
codesign --force --deep --options runtime --sign "$IDENTITY" "$APP"

# ------------------------------------------------------------------ #
# 4) Notary submission only when AEGIS_NOTARY_PROFILE is set
# ------------------------------------------------------------------ #
if [[ -z "${AEGIS_NOTARY_PROFILE:-}" ]]; then
  echo "NOTARY_SKIPPED"
  exit 0
fi

# Notary submission is attempted only when the profile env var is set.
# We do not claim notarized unless stapler validate would pass.
if ! command -v xcrun >/dev/null 2>&1; then
  echo "NOTARY_SKIPPED: xcrun not available"
  exit 0
fi

echo "NOTARY: submitting with profile AEGIS_NOTARY_PROFILE"
xcrun notarytool submit "$APP" --keychain-profile "$AEGIS_NOTARY_PROFILE" --wait || {
  echo "NOTARY_FAILED: submission did not complete; the app is not notarized"
  exit 0
}

# stapler validate — we do not claim notarized unless this would pass.
if ! xcrun stapler validate "$APP" >/dev/null 2>&1; then
  echo "NOTARY_STAPLER_FAILED: stapler did not validate; the app is not notarized"
  exit 0
fi

echo "NOTARY_OK: stapler validate passed"
