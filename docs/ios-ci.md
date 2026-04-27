# iOS CI — GitHub Actions

## Status (W18 / D-039)

The workflow is **gated behind a repository variable** so it does not consume
macOS minutes until OPS has signed off on the budget.

To enable: in GitHub → **Settings → Secrets and variables → Actions →
Variables**, add a repository variable `IOS_CI_ENABLED` with value `true`.
Once flipped, every push/PR matching the path filter will run a full
build + test on `macos-14`.

`workflow_dispatch` (manual run from the Actions tab) **always** runs and
ignores the variable, so engineers can validate without enabling automatic
runs.

## Cost Estimate

GitHub-hosted macOS runners are billed at **10x** Linux runners on private
repos. Free tier: ~200 macOS minutes/month at standard plan.

| Scenario | Wall time | Cost (per run) |
|----------|-----------|----------------|
| Cold cache | ~18-22 min | ~$1.60-2.00 |
| Warm cache (DerivedData + SPM hit) | ~10-14 min | ~$0.90-1.30 |
| Pre-booted simulator (warm) | -30 to -60s vs cold sim | included above |

Assuming ~30 PRs/month touching `ios/**` plus mainline pushes, expect
**$30-60/month** in macOS minutes. If that exceeds budget, options:

- Self-hosted Apple Silicon runner (one-time hardware ~$700 + power)
- Restrict trigger to `pull_request` only (skip `push` to main)
- Run only on PRs labelled `ios-test`

## Trigger Conditions

| Trigger | Condition |
|---------|-----------|
| Push to `main` / `ci/ios-green` | Only when `ios/**` files change AND `IOS_CI_ENABLED=true` |
| Pull request | Only when `ios/**` files change AND `IOS_CI_ENABLED=true` |
| Manual | `workflow_dispatch` (always runs, ignores the variable) |

## Scheme & Destination

- **Scheme**: `YiLuAn` (defined in `ios/project.yml` → `schemes.YiLuAn`)
- **Destination**: dynamically picked by `ios/scripts/pick_simulator.py`
  (avoids breakage when e.g. `iPhone 15 Pro` + iOS 18.x combo is unavailable)
- **Runner**: `macos-14` (Apple Silicon, M1)

## Pipeline Steps

1. Checkout → Setup Xcode (latest-stable) → Install XcodeGen via Homebrew
2. `xcodegen generate` — creates `.xcodeproj` from `ios/project.yml`
3. Restore caches: DerivedData + SPM
4. Resolve SPM dependencies
5. Pick a simulator UDID (robust picker, not hard-coded name+OS)
6. **Pre-boot the simulator** (`xcrun simctl boot` + `bootstatus -b`) to cut
   ~30-60s off the first `xcodebuild test` invocation
7. `xcodebuild test` with `CODE_SIGNING_ALLOWED=NO`, writes
   `TestResults.xcresult`
8. **Summarise xcresult** via `xcresulttool` → emits `::notice::` so
   pass/fail counts surface in the GH Actions UI without downloading the
   artifact
9. **Always** upload `TestResults.xcresult` + `xcodebuild.log` as artifact
   (run-id suffixed so re-runs do not collide)

## Local Reproduction

```bash
cd ios
brew install xcodegen        # one-time
xcodegen generate
xcodebuild test \
  -project YiLuAn.xcodeproj \
  -scheme YiLuAn \
  -destination 'platform=iOS Simulator,name=iPhone 15 Pro,OS=latest' \
  CODE_SIGNING_ALLOWED=NO
```

## Validation

The workflow yml passes `python -m yaml.safe_load`. Local `act` cannot
exercise the macos runner, so end-to-end validation must happen on
GitHub Actions itself; this is why the `IOS_CI_ENABLED` gate is the
recommended rollout path:

1. Flip `IOS_CI_ENABLED=true` on a quiet day.
2. Trigger via `workflow_dispatch` first; verify success.
3. Push a small `ios/**` change to confirm path filter + auto-trigger.
4. Watch a full week of macOS minute consumption.
5. If costs are acceptable, leave the variable on; otherwise flip it
   back to `false` and revisit options above.

## TestFlight — Next Steps

To extend this workflow for TestFlight submission:

1. Add an `archive` job gated on `main` push (not PRs)
2. Configure code signing: add `APPLE_CERTIFICATE`, `PROVISIONING_PROFILE`,
   and `APP_STORE_CONNECT_API_KEY` as repository secrets
3. Use `xcodebuild archive` → `xcodebuild -exportArchive` with an
   `ExportOptions.plist`
4. Upload to TestFlight via `xcrun altool --upload-app` or the App Store
   Connect API
5. Set `DEVELOPMENT_TEAM` in `project.yml` for archive builds
