# iOS CI — GitHub Actions

## Trigger Conditions

| Trigger | Condition |
|---------|-----------|
| Push to `main` | Only when `ios/**` files change |
| Pull request | Only when `ios/**` files change |
| Manual | `workflow_dispatch` (run from Actions tab) |

## Scheme & Destination

- **Scheme**: `YiLuAn` (defined in `ios/project.yml` → `schemes.YiLuAn`)
- **Destination**: `iPhone 15 Pro` simulator, latest iOS
- **Runner**: `macos-14` (Apple Silicon)

## Pipeline Steps

1. Checkout → Setup Xcode (latest-stable) → Install XcodeGen via Homebrew
2. `xcodegen generate` — creates `.xcodeproj` from `ios/project.yml`
3. Resolve SPM dependencies
4. `xcodebuild test` with `CODE_SIGNING_ALLOWED=NO`
5. On failure: upload `.xcresult` bundle as artifact

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

## TestFlight — Next Steps

To extend this workflow for TestFlight submission:

1. Add an `archive` job gated on `main` push (not PRs)
2. Configure code signing: add `APPLE_CERTIFICATE`, `PROVISIONING_PROFILE`, and `APP_STORE_CONNECT_API_KEY` as repository secrets
3. Use `xcodebuild archive` → `xcodebuild -exportArchive` with an `ExportOptions.plist`
4. Upload to TestFlight via `xcrun altool --upload-app` or the App Store Connect API
5. Set `DEVELOPMENT_TEAM` in `project.yml` for archive builds
