#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# generate_screenshots.sh — YiLuAn iOS App Store screenshot harness
#
# Drives Xcode UI Tests on multiple simulator devices to capture 5 screenshots
# per device, then renames + collects them into a single output directory ready
# for upload to App Store Connect.
#
# Requirements:
#   - macOS host with Xcode 15+
#   - xcbeautify (optional but recommended): `brew install xcbeautify`
#   - The UI test target `YiLuAnUITests` exposes an `AppStoreScreenshots`
#     test class with `test01_Login`, `test02_Home`, `test03_CompanionDetail`,
#     `test04_CreateOrder`, `test05_Chat` — each calling
#     `XCTAttachment(image: app.screenshot().image)` with a stable name.
#
# Usage:
#   ./generate_screenshots.sh                # all default devices
#   DEVICES="iPhone 15 Pro Max" ./generate_screenshots.sh
#   OUT=./screenshots-prod ./generate_screenshots.sh
#
# Output layout:
#   $OUT/
#     6.7-iphone-15-pro-max/01_login.png ... 05_chat.png
#     6.5-iphone-11-pro-max/...
#     5.5-iphone-8-plus/...
#     12.9-ipad-pro-12-9/...
# -----------------------------------------------------------------------------

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCHEME="YiLuAn"
TEST_PLAN="${TEST_PLAN:-Screenshots}"   # Optional: configure in Xcode
OUT="${OUT:-${PROJECT_DIR}/screenshots-out}"
DERIVED="${DERIVED:-${PROJECT_DIR}/.derived-screenshots}"

# Default device matrix (App Store required sizes).
# Adjust the simulator names to match `xcrun simctl list devices available`.
DEFAULT_DEVICES=(
  "iPhone 15 Pro Max|6.7-iphone-15-pro-max"
  "iPhone 11 Pro Max|6.5-iphone-11-pro-max"
  "iPhone 8 Plus|5.5-iphone-8-plus"
  "iPad Pro (12.9-inch) (6th generation)|12.9-ipad-pro-12-9"
)

if [[ -n "${DEVICES:-}" ]]; then
  IFS=',' read -r -a DEVICE_LIST <<< "${DEVICES}"
else
  DEVICE_LIST=("${DEFAULT_DEVICES[@]}")
fi

mkdir -p "$OUT"
mkdir -p "$DERIVED"

run_for_device() {
  local entry="$1"
  local sim_name="${entry%%|*}"
  local label="${entry##*|}"
  local target_dir="$OUT/$label"
  mkdir -p "$target_dir"

  echo "==> Running UI tests on '$sim_name' -> $target_dir"

  # 1) boot the simulator (idempotent)
  local udid
  udid="$(xcrun simctl list devices available | awk -v name="$sim_name" '
    $0 ~ "-- " {section=$0; next}
    index($0, name " (") == 1 { match($0, /\(([0-9A-F-]+)\)/, m); print m[1]; exit }
  ')"
  if [[ -z "$udid" ]]; then
    echo "!! simulator not found: $sim_name (skipping)"
    return 0
  fi
  xcrun simctl boot "$udid" 2>/dev/null || true
  xcrun simctl status_bar "$udid" override --time "9:41" --batteryState charged --batteryLevel 100 --cellularBars 4 --wifiBars 3 2>/dev/null || true

  # 2) run UI tests, attachments lifetime = keepAlways
  local pretty="cat"
  if command -v xcbeautify >/dev/null 2>&1; then pretty="xcbeautify"; fi

  set +e
  xcodebuild \
    -project "$PROJECT_DIR/YiLuAn.xcodeproj" \
    -scheme "$SCHEME" \
    -destination "platform=iOS Simulator,id=$udid" \
    -derivedDataPath "$DERIVED/$label" \
    -only-testing:YiLuAnUITests/AppStoreScreenshots \
    -resultBundlePath "$DERIVED/$label/result.xcresult" \
    test 2>&1 | $pretty
  local rc=${PIPESTATUS[0]}
  set -e
  if [[ $rc -ne 0 ]]; then
    echo "!! UI test run failed for $sim_name (rc=$rc); attachments may still be partial"
  fi

  # 3) extract attachments from the .xcresult
  python3 "$(dirname "$0")/extract_screenshots.py" \
    --xcresult "$DERIVED/$label/result.xcresult" \
    --out "$target_dir"
}

for entry in "${DEVICE_LIST[@]}"; do
  run_for_device "$entry"
done

echo "==> Done. Screenshots are under: $OUT"
