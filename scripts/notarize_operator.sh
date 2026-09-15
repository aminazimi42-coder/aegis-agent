#!/usr/bin/env bash
# T187 — Notary operator wrapper.
#
# Calls the existing submit helper (T183) then the existing staple
# helper (T184) in order.  Does not reimplement zip, submit, or staple.
# Does not pass Apple account, secret, team, or raw key flags to any
# helper.  Does not open Safari.  Does not upload anywhere except
# through the existing helpers.
#
# Without AEGIS_NOTARY_PROFILE the wrapper prints NOTARY_PROFILE_MISSING
# and the store-credentials pointer, then exits 0 so CI stays green.
# The success word for a stapled ticket is only ever printed by the
# staple helper when stapler validate exits 0; this wrapper never
# upgrades any other status to that word.

set -euo pipefail

# ------------------------------------------------------------------ #
# 0) Profile gate — without AEGIS_NOTARY_PROFILE, stop cleanly.
# ------------------------------------------------------------------ #
if [[ -z "${AEGIS_NOTARY_PROFILE:-}" ]]; then
  echo "NOTARY_PROFILE_MISSING"
  echo "To submit and staple, create a keychain profile on hermesdev:"
  echo "  See docs/APPLE_DEVELOPER.md for the store-credentials command."
  echo "  export AEGIS_NOTARY_PROFILE=aegis-notary"
  echo "  ./scripts/notarize_operator.sh"
  exit 0
fi

# ------------------------------------------------------------------ #
# 1) Run the submit helper, then the staple helper.
#    The helpers print their own status tokens; this wrapper does not
#    add its own.  Whatever the helpers print flows through.
# ------------------------------------------------------------------ #
./scripts/notarize_submit.sh
./scripts/notarize_staple.sh
