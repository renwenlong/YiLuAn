#!/usr/bin/env bash
#
# test_check_main_ci.sh — unit tests for check-main-ci.sh (ADR-0059 §5.5).
#
# Self-contained: builds check-runs fixtures on the fly, injects them via
# CHECK_RUNS_JSON, and asserts the gate's exit code for each scenario.
# No network, no real gh. Run: ./test_check_main_ci.sh
#
# Scenarios:
#   1. all 5 required success            → exit 0 (PASS)
#   2. one required failure              → exit 1 (abort)
#   3. one required pending (in_progress)→ exit 1 (abort)
#   4. one required MISSING (not run)    → exit 1 (abort)  [hardened vs ADR sketch]
#   5. one required skipped              → exit 1 (abort)
#   6. Postgres smoke MISSING            → exit 1 (abort)
#   7. extra non-required check red,     → exit 0 (PASS — only required gate)
#      all required green
#   8. malformed JSON                    → exit 2 (env error)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="${SCRIPT_DIR}/check-main-ci.sh"
TMPDIR_T="$(mktemp -d)"
trap 'rm -rf "${TMPDIR_T}"' EXIT

PASS=0
FAIL=0

# emit a check-runs JSON fixture from "name=conclusion" pairs.
# conclusion of "__omit__" skips that check entirely (MISSING case).
make_fixture() {
  local out="$1"; shift
  {
    printf '{"total_count":99,"check_runs":['
    local first=1
    for pair in "$@"; do
      local name="${pair%%=*}"
      local concl="${pair#*=}"
      [ "${concl}" = "__omit__" ] && continue
      [ "${first}" -eq 0 ] && printf ','
      first=0
      # in_progress/queued have null conclusion → emit status only
      if [ "${concl}" = "in_progress" ] || [ "${concl}" = "queued" ]; then
        printf '{"name":"%s","status":"%s","conclusion":null,"started_at":"2026-06-26T01:00:00Z"}' \
          "${name}" "${concl}"
      else
        printf '{"name":"%s","status":"completed","conclusion":"%s","started_at":"2026-06-26T01:00:00Z"}' \
          "${name}" "${concl}"
      fi
    done
    printf ']}'
  } > "${out}"
}

# run the gate with an injected fixture, assert exit code.
assert_exit() {
  local desc="$1"; local want="$2"; local fixture="$3"
  CHECK_RUNS_JSON="${fixture}" "${GATE}" --sha testsha >/dev/null 2>&1
  local got=$?
  if [ "${got}" -eq "${want}" ]; then
    echo "  ✅ ${desc} (exit ${got})"
    PASS=$((PASS+1))
  else
    echo "  ❌ ${desc} — want exit ${want}, got ${got}"
    FAIL=$((FAIL+1))
  fi
}

R1="Backend Tests"
R2="Docker Build Verification"
R3="WeChat Mini Program Tests"
R4="Build & Test (iOS Simulator)"
R5="Smoke tests (real Postgres + alembic)"

echo "═══ check-main-ci.sh unit tests ═══"

# 1. all green → PASS
make_fixture "${TMPDIR_T}/all_green.json" \
  "${R1}=success" "${R2}=success" "${R3}=success" "${R4}=success" \
  "${R5}=success"
assert_exit "all required success → PASS" 0 "${TMPDIR_T}/all_green.json"

# 2. one failure → abort
make_fixture "${TMPDIR_T}/one_fail.json" \
  "${R1}=success" "${R2}=failure" "${R3}=success" "${R4}=success" \
  "${R5}=success"
assert_exit "one required failure → abort" 1 "${TMPDIR_T}/one_fail.json"

# 3. one pending → abort
make_fixture "${TMPDIR_T}/one_pending.json" \
  "${R1}=success" "${R2}=success" "${R3}=in_progress" "${R4}=success" \
  "${R5}=success"
assert_exit "one required pending → abort" 1 "${TMPDIR_T}/one_pending.json"

# 4. one MISSING → abort (hardened: ADR `unique==[success]` would miss this)
make_fixture "${TMPDIR_T}/one_missing.json" \
  "${R1}=success" "${R2}=success" "${R3}=success" "${R4}=__omit__" \
  "${R5}=success"
assert_exit "one required MISSING → abort" 1 "${TMPDIR_T}/one_missing.json"

# 5. one skipped → abort
make_fixture "${TMPDIR_T}/one_skipped.json" \
  "${R1}=success" "${R2}=success" "${R3}=skipped" "${R4}=success" \
  "${R5}=success"
assert_exit "one required skipped → abort" 1 "${TMPDIR_T}/one_skipped.json"

# 6. newly required real-Postgres smoke missing → abort
make_fixture "${TMPDIR_T}/smoke_missing.json" \
  "${R1}=success" "${R2}=success" "${R3}=success" "${R4}=success" \
  "${R5}=__omit__"
assert_exit "Postgres smoke MISSING → abort" 1 "${TMPDIR_T}/smoke_missing.json"

# 7. extra non-required red, all required green → PASS (only required gate)
make_fixture "${TMPDIR_T}/extra_red.json" \
  "${R1}=success" "${R2}=success" "${R3}=success" "${R4}=success" \
  "${R5}=success" "Some Optional Check=failure" "Notify on CI failure=skipped"
assert_exit "extra non-required red, required all green → PASS" 0 "${TMPDIR_T}/extra_red.json"

# 8. malformed JSON → env error (exit 2)
printf 'not json at all' > "${TMPDIR_T}/bad.json"
assert_exit "malformed JSON → env error" 2 "${TMPDIR_T}/bad.json"

echo "─────────────────────────────────"
echo "PASS=${PASS} FAIL=${FAIL}"
[ "${FAIL}" -eq 0 ] || exit 1
echo "✅ all check-main-ci tests passed"
