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

Notarize is a later owner action after a signed app exists.  No notarize
ticket exists yet.  The codesign script prints `NOTARY_LOCKED_UNTIL_TICKET`
and does not invoke notarytool or stapler.

## What this does not do

- No Stripe. No payment processing in this repository.
- No license host URL is required for this slice.
