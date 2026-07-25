# Signing and notarization strategy

Research date: 2026-07-24

## Recommendation

OpenBeat should sign and notarize both direct-download installers in CI:

- **macOS:** enroll the release owner in the Apple Developer Program, sign the bundled PyInstaller executable with **Developer ID Application** and hardened runtime, build the package, sign the final package with **Developer ID Installer**, submit it with `notarytool`, staple the accepted ticket, then verify the signature, staple, and Gatekeeper assessment.
- **Windows:** use the **SignPath Foundation open-source program** if OpenBeat's submitted application is approved. Its managed pipeline and HSM-backed certificate are free for qualifying open-source projects. If approval is unavailable for launch, use **Azure Artifact Signing (Public Trust), Basic tier** only during a release month, authenticated from GitHub Actions with OIDC, and delete the Artifact Signing account afterward. Sign every shipped PE file (`.exe`/`.dll`) before assembling the installer, then sign and timestamp the final installer executable. Verify every signed artifact with the default Authenticode policy before upload.

This is the lowest-cost production path for the existing direct-download `.pkg` and `.exe` artifacts. It avoids a Windows private-key export or USB-token dependency and gives macOS Gatekeeper the expected Developer ID plus notarization chain.

## macOS

### Identity and cost

Direct distribution requires Apple Developer Program membership and a Developer ID identity. Apple lists membership at **USD 99 per membership year** (local pricing can vary); organization enrollment additionally requires legal-entity verification and normally a D‑U‑N‑S number. Apple also permits qualifying nonprofits, accredited educational institutions, and government entities to request a fee waiver. [Apple membership details](https://developer.apple.com/programs/whats-included/) and [enrollment requirements](https://developer.apple.com/programs/enroll/).

Use:

- `Developer ID Application` for the PyInstaller executable and any other executable code.
- `Developer ID Installer` for the completed flat `.pkg`.

Apple explicitly says Developer ID is for software distributed outside the Mac App Store. It also distinguishes app behavior after certificate expiry from installer behavior: an app signed while its Developer ID Application certificate was valid can continue to run after expiry, but a package signed with an expired Developer ID Installer certificate must be re-signed to launch. Revoked Developer ID code cannot be installed or launched. [Developer ID](https://developer.apple.com/support/developer-id/).

Enrollment and certificate issuance are external lead-time risks. Apple does not promise a fixed verification time on these pages, so the release schedule should allow contingency rather than assuming same-day setup.

### Required signing shape

Apple's current notarization requirements include:

- valid signing on every distributed executable;
- the appropriate Developer ID certificate, not Mac Distribution, ad hoc, Apple Development, or a local certificate;
- hardened runtime for app and command-line targets;
- a secure timestamp;
- no true `com.apple.security.get-task-allow` entitlement;
- a macOS 10.9-or-later SDK; and
- properly formatted entitlements.

The hardened runtime restricts injection, library loading, and executable memory. Exceptions should be granted only when the program demonstrably needs them. Apple says notarized submissions must enable it; for manual signing this is `codesign --options runtime`. [Hardened Runtime](https://developer.apple.com/documentation/security/hardened-runtime) and [notarization preparation](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution).

OpenBeat's current macOS payload has one PyInstaller CLI executable plus non-executable Lua scripts. The release pipeline should therefore:

1. Build the PyInstaller binary on macOS.
2. Sign the binary before copying it into the package root:

   ```bash
   codesign --force \
     --sign "Developer ID Application: <legal name> (<TEAM_ID>)" \
     --options runtime \
     --timestamp \
     dist/openbeat
   ```

3. Verify the inner code:

   ```bash
   codesign --verify --strict --verbose=2 dist/openbeat
   codesign --display --verbose=4 dist/openbeat
   ```

4. Build the unsigned component package with `pkgbuild` as today, then sign the final package. Either add `--sign "Developer ID Installer: …"` to `pkgbuild`, or use `productsign` afterward:

   ```bash
   productsign \
     --sign "Developer ID Installer: <legal name> (<TEAM_ID>)" \
     OpenBeat-macos-<version>-unsigned.pkg \
     OpenBeat-macos-<version>.pkg
   ```

5. Do not alter the package after signing.

Nested code must be signed **inside out**: sign each nested executable/framework/helper first and its enclosing bundle last. Do not use `codesign --deep` as the signing strategy; Apple notes that `--deep` only reaches nested code in particular standard locations. It remains useful as an additional diagnostic verification, not as a substitute for explicit signing. [Creating distribution-signed code for macOS](https://developer.apple.com/documentation/xcode/creating-distribution-signed-code-for-the-mac/) and [resolving notarization issues](https://developer.apple.com/documentation/security/resolving-common-notarization-issues).

### Notarization, stapling, and verification

Use `notarytool`; Apple stopped accepting `altool` and Xcode 13-or-earlier uploads on 2023-11-01. Notarization is an automated malware and signing check, not App Review. On acceptance Apple publishes a ticket that Gatekeeper can find and that can be stapled for offline verification. [Notarizing macOS software](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution).

Recommended CI sequence:

```bash
xcrun notarytool submit "OpenBeat-macos-<version>.pkg" \
  --keychain-profile "openbeat-notary" \
  --wait

xcrun stapler staple "OpenBeat-macos-<version>.pkg"
xcrun stapler validate "OpenBeat-macos-<version>.pkg"
pkgutil --check-signature "OpenBeat-macos-<version>.pkg"
spctl --assess --type install --verbose=4 "OpenBeat-macos-<version>.pkg"
```

Treat any non-accepted submission, failed staple, invalid certificate chain, or failed `spctl` assessment as a release failure. Retrieve and retain the notary log on rejection. Smoke-test the exact downloaded artifact on a clean supported macOS installation; notarization acceptance alone does not prove the installer works.

### CI credentials

GitHub's first-party guidance stores the base64-encoded `.p12`, its password, and a random temporary-keychain password as GitHub secrets, imports the certificate into a temporary keychain, and deletes that keychain on self-hosted runners. [GitHub: signing Apple applications](https://docs.github.com/en/actions/how-tos/deploy/deploy-to-third-party-platforms/sign-xcode-applications).

For OpenBeat:

- store the Developer ID Application and Installer identities as encrypted `.p12` secrets with strong, distinct export passwords;
- import them only in the protected release job on a macOS runner and a temporary keychain;
- restrict that job to protected version tags/environment approval; never expose signing secrets to pull-request jobs or untrusted forks;
- use an App Store Connect API key with `notarytool` where possible, or Apple ID plus app-specific password if necessary; store only the selected method's credentials;
- scope credentials to the release environment, redact logs, and destroy the temporary keychain in an `always()` cleanup step.

Certificate rotation is an operational runbook item: inventory expiry dates, renew before expiry, replace GitHub secrets, test a candidate release, and preserve the same Team ID/publisher identity. Timestamp all code. If compromise is suspected, revoke the certificate, remove the CI secret immediately, and reissue; previously revoked Developer ID code is no longer safe to distribute.

## Windows

### Recommended provider and cost

Use the **SignPath Foundation open-source program** if OpenBeat's application is approved. SignPath Foundation states that its signing service is free for qualifying open-source projects, that it verifies builds against the public source repository, and that signing keys are generated and stored in its HSM-backed service. This removes both the certificate fee and private-key custody burden. Approval and turnaround are not guaranteed, so it cannot be the only launch path. [SignPath Foundation](https://signpath.org/).

Use **Azure Artifact Signing**, formerly Trusted Signing, as the fallback. Microsoft recommends it for non-Store distribution. The Basic tier is **USD 9.99 per account per month**, includes 5,000 signatures/month and one certificate profile of each available type; additional signatures are USD 0.005 each. Premium is USD 99.99/month for 100,000 signatures and up to ten profiles of each type. Billing starts when the account is created and is not prorated. Prices remain estimates subject to agreement, region, currency, and tax. [Artifact Signing product and price](https://azure.microsoft.com/en-us/products/artifact-signing/) and [SKU details](https://learn.microsoft.com/en-us/azure/artifact-signing/how-to-change-sku).

OpenBeat does not need to keep an Azure Artifact Signing account continuously. Microsoft states that deleting the account stops renewal and future signing but does not affect certificates already used to sign files. Deleting a certificate profile likewise does not revoke previously issued certificates or invalidate their signatures. Therefore OpenBeat can pay for one full month, sign and RFC 3161 timestamp a release, verify and publish it, then delete the account. Do **not** revoke the certificate: Microsoft states that revocation makes affected signatures invalid from the selected revocation time. [Artifact Signing FAQ](https://learn.microsoft.com/en-us/azure/artifact-signing/faq) and [certificate revocation](https://learn.microsoft.com/en-us/azure/artifact-signing/how-to-cert-revocation).

At OpenBeat's expected cadence this makes Azure approximately USD 10 per release month rather than USD 120 per year: one annual release month costs about USD 10, two cost about USD 20, and quarterly release months cost about USD 40. Recreating the service may repeat account setup or identity-validation work, so planned release windows should include several business days and should sign any likely patch candidates before teardown.

Public Trust eligibility is currently limited to organizations in the USA, Canada, EU, and UK, and individuals in the USA and Canada. Identity validation must be completed in the Azure portal; billing legal name and address must match the intended certificate identity. Microsoft says to plan for a few business days for verification, but this is not a service-level guarantee. [Artifact Signing quickstart](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart) and [Windows signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options).

Artifact Signing holds keys in Microsoft-managed FIPS 140-2 Level 3 HSMs and manages certificate lifecycle. The official GitHub Action runs only on Windows runners (GitHub-hosted `windows-2022` and `windows-2025` are supported) and supports workload identity/OIDC. [Azure Artifact Signing](https://azure.microsoft.com/en-us/products/artifact-signing/) and [official Artifact Signing Action](https://github.com/Azure/artifact-signing-action).

### SmartScreen expectations

Signing is necessary but does **not** guarantee a warning-free first download. Microsoft says SmartScreen evaluates publisher reputation and file-hash reputation. A new signed binary can remain “unrecognized” until reputation accumulates. OV and EV behave the same for this purpose; EV no longer receives automatic positive reputation. Unsigned and self-signed programs receive the same warning class, and enterprise policy can prevent bypass. [SmartScreen reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation).

Operational consequences:

- sign every release under one stable verified publisher identity;
- avoid switching identity/provider without cause, because continuity contributes to the publisher signal;
- warn early adopters that a new project may initially trigger SmartScreen;
- never sign experimental, potentially unwanted, or third-party binaries outside the controlled release graph;
- do not claim that EV or Artifact Signing guarantees instant reputation.

The Microsoft Store is the only documented route in this option set that reliably avoids SmartScreen download warnings because Store submissions are signed by Microsoft. It is not the recommendation here because OpenBeat's current destination is direct GitHub `.exe` distribution, but it remains a future distribution option.

### Packaging and signing order

OpenBeat currently builds a PyInstaller **onedir** runtime, embeds it in a second PyInstaller **onefile/windowed** installer, and publishes the outer installer. The defensible signing order is:

1. Build the runtime directory.
2. Sign and RFC 3161 timestamp every shipped Authenticode-capable `.exe` and `.dll` in that directory.
3. Verify those files.
4. Build the final installer around the signed payload.
5. Sign and RFC 3161 timestamp the final `OpenBeat-windows-<version>-installer.exe`.
6. Verify the final installer, then hash and upload it without further modification.

Signing the inner files before packaging preserves their publisher identity after installation. Signing the outer installer separately authenticates the downloaded container. Any byte-changing operation after signing can invalidate that file's signature.

For a traditional certificate, equivalent SignTool behavior is:

```powershell
signtool sign /fd SHA256 /tr <RFC3161_TIMESTAMP_URL> /td SHA256 <file>
signtool verify /pa /all /v <file>
```

Recent Windows SDK SignTool versions require explicit file and timestamp digest algorithms; Microsoft recommends SHA-256. `/pa` selects the default Authenticode verification policy (without it, SignTool uses driver policy), and `/all` verifies every signature. SignTool returns `0` for success, `1` for failure, and `2` for warnings; CI should accept only `0`. [SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool).

With Artifact Signing, use `azure/artifact-signing-action@v2`, target both `exe,dll` for the inner pass and the final installer for the outer pass, and request SHA-256. Keep signing as a distinct, protected release stage; do not run arbitrary code after it with access to signing authority.

### CI identity and rotation

Use GitHub OIDC federation rather than a client secret. GitHub documents that OIDC allows Actions to access Azure without storing long-lived Azure credentials, and requires `id-token: write` plus a cloud-side trust restricted by claims/conditions. The official Artifact Signing Action recommends OIDC. [GitHub OIDC with Azure](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-azure) and [official Artifact Signing Action](https://github.com/Azure/artifact-signing-action).

Grant the federated principal only the Artifact Signing certificate-profile signer role at the narrowest resource scope. Restrict the federated subject to this repository's protected release environment or tag workflow; do not authorize all branches. Use environment approval for production signing.

Artifact Signing manages short-lived signing certificates, so there is no exported Windows private key to rotate in GitHub. Rotation instead means maintaining the Azure identity validation/profile, reviewing federated credentials and RBAC, preserving the verified publisher identity, and removing stale federated subjects. Timestamp every signature so validation is anchored to signing time. If the profile or workflow is compromised, disable the federated credential/profile immediately, investigate signed artifacts, and create a replacement trust path.

## Rejected alternatives

| Alternative | Why not selected |
| --- | --- |
| Unsigned downloads | Gatekeeper and SmartScreen friction; no publisher identity or tamper evidence. Microsoft explicitly does not recommend unsigned public distribution. |
| Self-signed certificates | Not publicly trusted. Microsoft documents the same SmartScreen behavior as unsigned software; Apple notarization requires an appropriate Developer ID certificate. |
| Windows EV certificate | More costly and more rigorous validation, but Microsoft says EV no longer bypasses SmartScreen and has the same reputation-building behavior as OV. It may still matter for a particular enterprise procurement requirement, not for OpenBeat's current consumer download goal. |
| Traditional Windows OV certificate | Viable fallback if Artifact Signing eligibility fails, but Microsoft estimates USD 150–300/year, several business days of validation, and an HSM/hardware-token requirement under current CA/Browser Forum rules. It adds key custody and CI integration work. [Microsoft Windows signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options). |
| Microsoft Store only | Store signing avoids SmartScreen download warnings, but changes the distribution and packaging channel rather than securing the existing GitHub-hosted installer. Evaluate separately if Store distribution becomes a product goal. |
| Mac App Store | Changes sandboxing, review, packaging, and distribution requirements; it is not a substitute for Developer ID signing of the current direct-download package. |
| `codesign --deep` as the macOS signing implementation | Apple says it only traverses nested content in specific standard bundle locations. Explicit inside-out signing is auditable and robust; `--deep` can remain a verification diagnostic. |
| `altool` notarization | Unsupported for submissions since 2023-11-01; use `notarytool`. |
| Keeping Azure Artifact Signing active year-round | Unnecessary for OpenBeat's expected release volume. Timestamped installers remain signed after account deletion, so activate the paid service only for release months if SignPath is unavailable. |

## Setup-time and release gates

One-time setup should be scheduled before the first public release:

- Apple enrollment/legal verification, two Developer ID certificates, CI secret import, and a dry-run notarization.
- SignPath Foundation approval and its repository-connected signing policy; the application has been submitted and is pending review.
- As fallback, Azure subscription/provider registration, identity validation, signing account/profile, narrow RBAC, GitHub OIDC federation, and a dry-run signed installer. Delete the Artifact Signing account after the release is signed and verified unless another release is imminent.
- Clean-machine installation tests on supported macOS and Windows versions.

Neither Apple nor Microsoft promises completion by a specific day in the cited onboarding material. Budget at least several business days of calendar slack, and do not announce a release date until both identities can sign a test build end to end.

Make these hard release gates:

- all inner native executables and the outer installer have valid expected-publisher signatures;
- macOS notarization is accepted and stapling/Gatekeeper assessment succeeds;
- Windows `signtool verify /pa /all /v` returns success for inner files and outer installer;
- exact post-signing artifacts pass installation smoke tests;
- published SHA-256 checksums are calculated only after all signing/stapling is complete.
