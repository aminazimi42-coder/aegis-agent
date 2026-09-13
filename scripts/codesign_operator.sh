#!/usr/bin/env bash
# T158/T167/T167_CONTINUE — Codesign the Aegis Operator.app only when a
# Developer ID Application identity exists in the keychain.
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
# This script does not invoke notarytool.  It does not invoke stapler.
# It prints NOTARY_LOCKED_UNTIL_TICKET and exits 0.
#
# This script does not open Safari and does not upload anywhere.
# Never writes the word notarized as a success state.

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
# 5) Notarize is a later owner action — no ticket exists yet.
# ------------------------------------------------------------------ #
echo "NOTARY_LOCKED_UNTIL_TICKET"
exit 0
