# Apple Developer ID

## Identity

- **Team ID:** 3J54UZPZW3
- **Identity name:** Developer ID Application: Amin Azimi

## Enrollment

The owner enrolls in the Apple Developer Program at
<https://developer.apple.com/programs/> on the **hermesdev** account — not
the amin account.

An annual fee applies; the exact amount and payment date are not recorded
in this repository.

## After enrollment

1. The owner creates a **Developer ID Application** certificate in the Apple
   account.
2. The owner installs the certificate into the **hermesdev** keychain.
3. The owner reruns `scripts/codesign_operator.sh` from the repo on
   hermesdev.

Signing does not happen on the amin operator account.

## Raw certificate files

Raw `.cer`, `.csr`, `.p12`, and `.p8` files stay in Downloads or the
Keychain on hermesdev.  They are never copied into the git repository.

## Notarize

On **hermesdev** only, the owner creates a notarytool keychain profile with
`xcrun notarytool store-credentials` and exports the profile name as
`AEGIS_NOTARY_PROFILE` in the environment.  The codesign script submits to
notarytool with that keychain profile only — no Apple ID or password flags
are passed.  After notarytool reports Accepted, the script runs
`stapler staple` then `stapler validate`; it prints `NOTARIZED` only if
`stapler validate` exits 0.  Without the profile the script prints
`NOTARY_SKIPPED` and exits 0.

The profile name stays in the environment, never in git.

Signing and notarizing happen on **hermesdev**, never on the **amin** account.

No dollar amount or payment date is recorded in this repository.  No Stripe
and no license host URL are required for this slice.
