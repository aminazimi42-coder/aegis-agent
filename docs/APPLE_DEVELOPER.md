# Apple Developer ID

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

## What this does not do

- No Stripe. No payment processing in this repository.
- No license host URL is required for this slice.
- Notarization is locked until T168. The codesign script prints
  `NOTARY_LOCKED_UNTIL_T168` and does not call notarytool.
