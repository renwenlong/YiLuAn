#!/usr/bin/env -S -i /bin/bash --noprofile --norc
# Restricted staging redeploy entry point (ADR-0059, access model I-3).
# The environment is cleared by the shebang launcher before Bash starts, so
# BASH_ENV and inherited shell-option variables cannot run startup code.
#
# Install this file as a root-owned executable outside the repository. The
# dedicated deploy identity may invoke it with exactly one full origin/main
# commit SHA; it does not provide an interactive shell.

set -Eeuo pipefail

readonly PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
readonly REPO_DIR="/srv/yiluan"
readonly DEPLOY_HOME="/var/lib/yiluan-deploy"
readonly CI_GATE="/usr/local/libexec/yiluan-staging-deploy/check-main-ci.sh"
readonly AUDIT_LOG="/var/log/yiluan-staging-redeploy.log"
readonly LOCK_FILE="/var/lock/yiluan-staging-redeploy.lock"
readonly LSATTR="/usr/bin/lsattr"
export PATH

stage="initialization"
target_sha="unvalidated"
audit_available=false

audit() {
  local result="$1"
  local detail="$2"
  local timestamp operator

  timestamp="$(env -i PATH="$PATH" /bin/date -u +'%Y-%m-%dT%H:%M:%SZ')"
  operator="$(env -i PATH="$PATH" /usr/bin/id -un)"
  printf '%s operator=%s target_sha=%s result=%s detail=%s\n' \
    "$timestamp" "$operator" "$target_sha" "$result" "$detail" >>"$AUDIT_LOG"
}

audit_failure_on_exit() {
  local exit_code=$?

  trap - EXIT
  if [[ "$exit_code" -ne 0 && "$audit_available" == true ]]; then
    audit "FAILED" "$stage" || true
  fi
  exit "$exit_code"
}
trap audit_failure_on_exit EXIT

run_clean() {
  env -i \
    HOME="$DEPLOY_HOME" \
    LANG="C.UTF-8" \
    PATH="$PATH" \
    "$@"
}

stage="validating append-only audit sink"
if [[ ! -f "$AUDIT_LOG" || ! -w "$AUDIT_LOG" ]]; then
  echo "audit log is missing or not writable: $AUDIT_LOG" >&2
  exit 1
fi
if ! audit_attributes="$(run_clean "$LSATTR" -d "$AUDIT_LOG")"; then
  echo "cannot verify append-only audit log: $AUDIT_LOG" >&2
  exit 1
fi
audit_flags="${audit_attributes%%[[:space:]]*}"
if [[ "$audit_flags" != *a* ]]; then
  echo "audit log is not append-only: $AUDIT_LOG" >&2
  exit 1
fi
audit_available=true

stage="validating invocation"
if [[ $# -ne 1 ]]; then
  echo "usage: $(basename "$0") <40-character-origin-main-sha>" >&2
  exit 2
fi

target_sha="$1"
if [[ ! "$target_sha" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "target must be one full 40-character Git commit SHA" >&2
  exit 2
fi
target_sha="${target_sha,,}"

stage="acquiring deployment lock"
exec 9>"$LOCK_FILE"
if ! run_clean flock -n 9; then
  echo "another staging redeploy is already running" >&2
  exit 1
fi

audit "STARTED" "requested"

stage="validating repository"
run_clean git -C "$REPO_DIR" rev-parse --is-inside-work-tree >/dev/null
worktree_status="$(
  run_clean git -C "$REPO_DIR" status --porcelain=v1 --untracked-files=all
)"
if [[ -n "$worktree_status" ]]; then
  echo "deployment checkout is not clean" >&2
  exit 1
fi

stage="fetching origin/main"
run_clean git -C "$REPO_DIR" fetch --quiet --prune origin main

stage="validating target SHA"
resolved_sha="$(run_clean git -C "$REPO_DIR" rev-parse --verify "${target_sha}^{commit}")"
if [[ "${resolved_sha,,}" != "$target_sha" ]]; then
  echo "target does not resolve to the exact requested commit" >&2
  exit 1
fi
main_sha="$(
  run_clean git -C "$REPO_DIR" rev-parse --verify refs/remotes/origin/main
)"
if [[ "${main_sha,,}" != "$target_sha" ]]; then
  echo "target must equal the current origin/main commit" >&2
  exit 1
fi

stage="checking required CI"
run_clean "$CI_GATE" --sha "$target_sha" --repo renwenlong/YiLuAn

stage="checking out target SHA"
run_clean git -C "$REPO_DIR" checkout --quiet --detach "$target_sha"

stage="deploying staging"
run_clean "$REPO_DIR/deploy/up.sh" staging

stage="checking API ping"
run_clean curl -fsS --max-time 10 http://127.0.0.1:18080/api/v1/ping >/dev/null
stage="checking health"
run_clean curl -fsS --max-time 10 http://127.0.0.1:18080/health >/dev/null
stage="checking readiness"
run_clean curl -fsS --max-time 10 http://127.0.0.1:18080/readiness >/dev/null
stage="checking mock pay"
run_clean curl -fsS --max-time 10 \
  http://127.0.0.1:18080/__staging/mock-pay/health >/dev/null
stage="checking mock SMS"
run_clean curl -fsS --max-time 10 \
  http://127.0.0.1:18080/__staging/mock-sms/health >/dev/null

stage="writing completion audit"
audit "PASSED" "ci=5/5,health=5/5"
echo "staging redeploy passed for $target_sha"
