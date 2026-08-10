#!/usr/bin/env bash
#
# check-main-ci.sh — Pre-deploy CI gate (ADR-0059 §5.5).
#
# Verifies that a target commit's REQUIRED GitHub checks are all green
# before that commit is deployed to staging. Prevents a red / pending
# commit from polluting the QA (刻晴) staging environment.
#
# Design notes (stricter than the ADR-0059 §5.5 sketch):
#   - Validates the TARGET commit SHA (the one about to be deployed),
#     not "the latest arbitrary run".
#   - Checks each REQUIRED check by name INDIVIDUALLY: a required check
#     that is MISSING (never ran / not reported) is treated as a hard
#     failure, not silently ignored. (The `unique == ["success"]` trick
#     in the ADR sketch can pass even when a required check is absent.)
#   - Only conclusion == "success" passes. pending / failure / cancelled
#     / timed_out / skipped / neutral all abort.
#
# Required checks mirror the GitHub branch-protection required status checks
# for `main` (authoritative source), as of 2026-08-10:
#   - Backend Tests
#   - Docker Build Verification
#   - WeChat Mini Program Tests
#   - Build & Test (iOS Simulator)
#   - Smoke tests (real Postgres + alembic)
#
# Keep this list synchronized with branch protection. A newly required check
# must fail closed here until it is explicitly added and covered by this
# script's fixture tests.
#
# Usage:
#   ./check-main-ci.sh [--sha <commit-sha>] [--repo <owner/repo>]
#
#   --sha   Commit SHA to gate on. Default: `git rev-parse HEAD`.
#   --repo  owner/repo for the gh API. Default: renwenlong/YiLuAn.
#
# Testability:
#   Set CHECK_RUNS_JSON=/path/to/fixture.json to inject a check-runs API
#   response (the `{"check_runs":[...]}` shape) and bypass the live `gh`
#   call. Used by deploy/staging/test_check_main_ci.sh.
#
# Dependencies: bash, python3 (JSON parsing via _parse_required_checks.py).
# gh only when CHECK_RUNS_JSON is unset. Deliberately avoids jq (not
# present on all hosts).
#
# Exit codes:
#   0  all required checks present and success → safe to deploy
#   1  one or more required checks missing / not success → abort deploy
#   2  usage / environment error (missing gh/python3, bad args, API failure)

set -euo pipefail

REPO_DEFAULT="renwenlong/YiLuAn"

# --- required checks (authoritative: branch protection on main) ---------
REQUIRED_CHECKS=(
  "Backend Tests"
  "Docker Build Verification"
  "WeChat Mini Program Tests"
  "Build & Test (iOS Simulator)"
  "Smoke tests (real Postgres + alembic)"
)

# --- arg parsing --------------------------------------------------------
SHA=""
REPO="${REPO_DEFAULT}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --sha)
      SHA="${2:-}"; shift 2 ;;
    --repo)
      REPO="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,44p' "$0"; exit 0 ;;
    *)
      echo "❌ unknown argument: $1" >&2; exit 2 ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ python3 not found — required for JSON parsing" >&2
  exit 2
fi

if [ -z "${SHA}" ]; then
  if ! SHA="$(git rev-parse HEAD 2>/dev/null)"; then
    echo "❌ no --sha given and 'git rev-parse HEAD' failed (not a git repo?)" >&2
    exit 2
  fi
fi

# --- fetch check-runs JSON ---------------------------------------------
# CHECK_RUNS_JSON (env) injects a fixture for testing; otherwise call gh.
if [ -n "${CHECK_RUNS_JSON:-}" ]; then
  if [ ! -f "${CHECK_RUNS_JSON}" ]; then
    echo "❌ CHECK_RUNS_JSON points to a missing file: ${CHECK_RUNS_JSON}" >&2
    exit 2
  fi
  RUNS_JSON="$(cat "${CHECK_RUNS_JSON}")"
else
  if ! command -v gh >/dev/null 2>&1; then
    echo "❌ gh CLI not found and CHECK_RUNS_JSON not set — cannot query CI status" >&2
    exit 2
  fi
  # No --paginate: it concatenates per-page JSON objects and breaks a
  # single-object parse. check-runs returns up to 30/page; the repo has
  # ~13 checks, well within one page.
  if ! RUNS_JSON="$(gh api "repos/${REPO}/commits/${SHA}/check-runs" 2>/dev/null)"; then
    echo "❌ gh api call failed for repos/${REPO}/commits/${SHA}/check-runs" >&2
    exit 2
  fi
fi

# --- evaluate each required check individually --------------------------
# Delegate JSON parsing to the standalone helper so stdin carries ONLY the
# check-runs JSON (no here-doc/stdin conflict). The helper prints one
# "NAME\tCONCLUSION" line per required check; MISSING when absent.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! RESULT="$(printf '%s' "${RUNS_JSON}" | python3 "${SCRIPT_DIR}/_parse_required_checks.py" "${REQUIRED_CHECKS[@]}")"; then
  echo "❌ failed to parse check-runs JSON" >&2
  exit 2
fi

echo "🔎 CI gate for ${REPO}@${SHA}"
echo "   required checks: ${#REQUIRED_CHECKS[@]}"

FAILED=0
while IFS=$'\t' read -r name conclusion; do
  [ -z "${name}" ] && continue
  if [ "${conclusion}" = "success" ]; then
    echo "   ✅ ${name}: success"
  elif [ "${conclusion}" = "MISSING" ]; then
    echo "   ❌ ${name}: MISSING (required check did not run)"
    FAILED=1
  else
    echo "   ❌ ${name}: ${conclusion} (not success)"
    FAILED=1
  fi
done <<< "${RESULT}"

if [ "${FAILED}" -ne 0 ]; then
  echo "❌ CI gate FAILED for ${SHA} — aborting deploy (one or more required checks not green)" >&2
  exit 1
fi

echo "✅ CI gate PASSED for ${SHA} — all required checks green, safe to deploy"
exit 0
