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

## Notarize

After signing succeeds, the owner can notarize the app:

1. The owner creates a notarytool keychain profile on the **hermesdev**
   account:

   ```bash
   xcrun notarytool store-credentials "aegis-notary-profile" \
     --apple-id <hermesdev-apple-id> \
     --team-id <team-id> \
     --password <app-specific-password>
   ```

2. The owner exports the profile name so the codesign script can use it:

   ```bash
   export AEGIS_NOTARY_PROFILE="aegis-notary-profile"
   ```

3. The owner reruns `scripts/codesign_operator.sh` from the repo on
   hermesdev.  The script submits to notarytool using the keychain
   profile, waits for Apple to report Accepted, then runs `stapler
   staple` and `stapler validate` on the app.  It prints NOTARIZED only
   if `stapler validate` succeeds; otherwise it prints NOTARY_PENDING or
   NOTARY_FAILED and exits 0.

## What this does not do

- No Stripe. No payment processing in this repository.
- No license host URL is required for this slice.
- Notarization only runs when `AEGIS_NOTARY_PROFILE` is set; without it
  the script prints `NOTARY_SKIPPED`.
