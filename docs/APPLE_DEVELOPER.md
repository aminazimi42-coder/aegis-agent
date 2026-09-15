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

## Notarize — hermesdev-only steps

1. On **hermesdev** only, the owner creates a notarytool keychain profile:
   `xcrun notarytool store-credentials` — the profile stays on the keychain.
2. Export the profile name as `AEGIS_NOTARY_PROFILE` in the environment.
3. Rerun `scripts/codesign_operator.sh` — it submits to notarytool with
   `--keychain-profile` only (no `--apple-id`, no `--password`, no API-key
   file path committed).
4. Wait for Apple to report Accepted, then the script runs
   `stapler staple` and `stapler validate`.
5. `NOTARIZED` prints only if `stapler validate` exits 0; otherwise the
   script prints `NOTARY_PENDING` or `NOTARY_FAILED` and exits 0.

The profile name is an environment variable — never a committed secret.

Never run this on the **amin** operator account.

## Submit (T183)

A separate submit-only helper (`scripts/notarize_submit.sh`) sends the
already-signed app to Apple Notary and prints a submission id.  Waiting
for Apple's verdict and stapling the ticket are NOT in this slice.

### Create the keychain profile on hermesdev only, not amin

```bash
xcrun notarytool store-credentials "aegis-notary" \
  --apple-id "aminazimi42@icloud.com" \
  --team-id "3J54UZPZW3"
```

Apple will ask for an app-specific password.  That password never
enters git.

### Then submit

```bash
export AEGIS_NOTARY_PROFILE=aegis-notary
./scripts/notarize_submit.sh
```

The script verifies the signature with `codesign --verify --deep --strict`,
builds a zip with `ditto`, and submits with `--keychain-profile` only —
no `--apple-id`, no `--password`, no `--team-id` flags on the submit
command.  It prints `NOTARY_SUBMITTED: <id>` on success or
`NOTARY_PROFILE_MISSING` and exits 0 when the profile is absent.

Still enroll, sign, and submit on hermesdev.  The shared drop box is
not the submit machine.

No dollar amount.  No pay date.  No Stripe.  No license host.  No App
Store claim.

## Raw certificate files (repeated)

Raw `.cer`, `.csr`, `.p12`, and `.p8` files stay in Downloads or the
Keychain on hermesdev.  They are never copied into the git repository.

No dollar amount or payment date is recorded in this repository.  No Stripe
and no license host URL are required for this slice.
