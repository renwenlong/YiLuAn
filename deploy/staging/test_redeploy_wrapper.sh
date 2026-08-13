#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER="$SCRIPT_DIR/redeploy-wrapper.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

passed=0
failed=0

fail() {
  echo "not ok - $1" >&2
  failed=$((failed + 1))
}

pass() {
  echo "ok - $1"
  passed=$((passed + 1))
}

assert_fails() {
  local name="$1"
  shift
  if "$@" >"$TMP/output" 2>&1; then
    fail "$name"
  else
    pass "$name"
  fi
}

assert_succeeds() {
  local name="$1"
  shift
  if "$@" >"$TMP/output" 2>&1; then
    pass "$name"
  else
    cat "$TMP/output" >&2
    fail "$name"
  fi
}

assert_fails_and_audits() {
  local name="$1"
  shift
  local before after
  before="$(wc -l <"$TMP/audit.log")"
  assert_fails "$name" "$@"
  after="$(wc -l <"$TMP/audit.log")"
  if [[ "$after" -gt "$before" ]] \
    && tail -n "$((after - before))" "$TMP/audit.log" \
      | grep -q 'result=FAILED'; then
    pass "$name is audited"
  else
    fail "$name is audited"
  fi
}

mkdir -p "$TMP/bin" "$TMP/home" "$TMP/libexec"
git init --bare -q "$TMP/origin.git"
git clone -q "$TMP/origin.git" "$TMP/seed"
git -C "$TMP/seed" config user.name test
git -C "$TMP/seed" config user.email test@example.invalid
mkdir -p "$TMP/seed/deploy"
cat >"$TMP/seed/deploy/up.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
printf '%s|%s\n' "\$1" "\${DOCKER_HOST-unset}" >>"$TMP/deploy-calls"
[[ ! -f "$TMP/deploy-fail" ]]
EOF
chmod +x "$TMP/seed/deploy/up.sh"
echo initial >"$TMP/seed/README"
git -C "$TMP/seed" add .
git -C "$TMP/seed" commit -qm initial
git -C "$TMP/seed" branch -M main
git -C "$TMP/seed" push -q -u origin main
old_main_sha="$(git -C "$TMP/seed" rev-parse HEAD)"
echo current >"$TMP/seed/CURRENT"
git -C "$TMP/seed" add CURRENT
git -C "$TMP/seed" commit -qm current
git -C "$TMP/seed" push -q origin main
git --git-dir="$TMP/origin.git" symbolic-ref HEAD refs/heads/main
git clone -q "$TMP/origin.git" "$TMP/repo"
main_sha="$(git -C "$TMP/repo" rev-parse HEAD)"

git -C "$TMP/seed" checkout -qb side
echo side >"$TMP/seed/SIDE"
git -C "$TMP/seed" add SIDE
git -C "$TMP/seed" commit -qm side
side_sha="$(git -C "$TMP/seed" rev-parse HEAD)"
git -C "$TMP/seed" push -q origin side
git -C "$TMP/repo" fetch -q origin side

cat >"$TMP/libexec/check-main-ci.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "\$*" >>"$TMP/ci-calls"
[[ ! -f "$TMP/ci-fail" ]]
EOF
chmod +x "$TMP/libexec/check-main-ci.sh"

cat >"$TMP/bin/curl" <<EOF
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "\${*: -1}" >>"$TMP/curl-calls"
[[ ! -f "$TMP/curl-fail" ]]
EOF
chmod +x "$TMP/bin/curl"

cat >"$TMP/bin/lsattr" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [[ -f "$TMP/audit-not-append-only" ]]; then
  printf '%s %s\n' '----------------------' "\${*: -1}"
else
  printf '%s %s\n' '-----a----------------' "\${*: -1}"
fi
EOF
chmod +x "$TMP/bin/lsattr"

cp "$WRAPPER" "$TMP/wrapper"
sed -i \
  -e "s|readonly PATH=.*|readonly PATH=\"$TMP/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\"|" \
  -e "s|readonly REPO_DIR=.*|readonly REPO_DIR=\"$TMP/repo\"|" \
  -e "s|readonly DEPLOY_HOME=.*|readonly DEPLOY_HOME=\"$TMP/home\"|" \
  -e "s|readonly CI_GATE=.*|readonly CI_GATE=\"$TMP/libexec/check-main-ci.sh\"|" \
  -e "s|readonly AUDIT_LOG=.*|readonly AUDIT_LOG=\"$TMP/audit.log\"|" \
  -e "s|readonly LOCK_FILE=.*|readonly LOCK_FILE=\"$TMP/deploy.lock\"|" \
  -e "s|readonly LSATTR=.*|readonly LSATTR=\"$TMP/bin/lsattr\"|" \
  "$TMP/wrapper"
chmod +x "$TMP/wrapper"
touch "$TMP/audit.log"

touch "$TMP/audit-not-append-only"
assert_fails "rejects audit log without append-only protection" \
  "$TMP/wrapper" "$main_sha"
grep -q "audit log is not append-only" "$TMP/output" \
  && pass "reports missing append-only protection" \
  || fail "reports missing append-only protection"
[[ ! -s "$TMP/audit.log" ]] \
  && pass "does not trust unsafe audit sink" \
  || fail "does not trust unsafe audit sink"
rm "$TMP/audit-not-append-only"

cat >"$TMP/malicious-bash-env" <<EOF
printf '%s\n' sourced >"$TMP/bash-env-sourced"
exit 0
EOF
mkdir "$TMP/hostile-bin"
cat >"$TMP/hostile-bin/bash" <<EOF
#!/bin/sh
printf '%s\n' selected >"$TMP/hostile-bash-selected"
exit 0
EOF
chmod +x "$TMP/hostile-bin/bash"
assert_fails_and_audits "rejects missing SHA despite hostile startup environment" \
  env PATH="$TMP/hostile-bin" BASH_ENV="$TMP/malicious-bash-env" \
    "$TMP/wrapper"
[[ ! -e "$TMP/bash-env-sourced" ]] \
  && pass "BASH_ENV startup injection is ignored" \
  || fail "BASH_ENV startup injection is ignored"
[[ ! -e "$TMP/hostile-bash-selected" ]] \
  && pass "hostile PATH cannot select the Bash interpreter" \
  || fail "hostile PATH cannot select the Bash interpreter"
assert_fails_and_audits "rejects extra arguments" \
  "$TMP/wrapper" "$main_sha" extra
assert_fails_and_audits "rejects abbreviated SHA" \
  "$TMP/wrapper" "${main_sha:0:12}"
assert_fails_and_audits "rejects non-main commit" "$TMP/wrapper" "$side_sha"
assert_fails_and_audits "rejects old origin/main ancestor" \
  "$TMP/wrapper" "$old_main_sha"

echo dirty >>"$TMP/repo/README"
assert_fails_and_audits "rejects dirty tracked worktree" \
  "$TMP/wrapper" "$main_sha"
git -C "$TMP/repo" checkout -q -- README
touch "$TMP/repo/UNTRACKED"
assert_fails_and_audits "rejects untracked worktree file" \
  "$TMP/wrapper" "$main_sha"
rm "$TMP/repo/UNTRACKED"

touch "$TMP/ci-fail"
assert_fails_and_audits "CI failure prevents deployment" \
  "$TMP/wrapper" "$main_sha"
if [[ -e "$TMP/deploy-calls" ]]; then
  fail "CI failure made no deploy call"
else
  pass "CI failure made no deploy call"
fi
rm "$TMP/ci-fail"

touch "$TMP/deploy-fail"
assert_fails_and_audits "deployment command failure is rejected" \
  "$TMP/wrapper" "$main_sha"
rm "$TMP/deploy-fail"

touch "$TMP/curl-fail"
assert_fails_and_audits "health probe failure is rejected" \
  "$TMP/wrapper" "$main_sha"
rm "$TMP/curl-fail"
: >"$TMP/deploy-calls"
: >"$TMP/curl-calls"

assert_succeeds "valid main SHA deploys" \
  env DOCKER_HOST=tcp://attacker.invalid:2375 "$TMP/wrapper" "$main_sha"
[[ "$(cat "$TMP/deploy-calls")" == "staging|unset" ]] \
  && pass "deploy command is fixed and caller environment is cleared" \
  || fail "deploy command is fixed and caller environment is cleared"
[[ "$(wc -l <"$TMP/curl-calls")" -eq 5 ]] \
  && pass "all five health probes ran" \
  || fail "all five health probes ran"
grep -q "target_sha=$main_sha result=FAILED detail=checking required CI" \
  "$TMP/audit.log" \
  && pass "CI rejection is audited" \
  || fail "CI rejection is audited"
grep -q "target_sha=$main_sha result=PASSED detail=ci=5/5,health=5/5" \
  "$TMP/audit.log" \
  && pass "success audit contains SHA and gate results" \
  || fail "success audit contains SHA and gate results"

echo "1..$((passed + failed))"
echo "passed=$passed failed=$failed"
[[ "$failed" -eq 0 ]]
