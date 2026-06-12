"""E#9 lint hard gate: every mutating endpoint (POST/PUT/PATCH/DELETE) with
a user-side identity dependency MUST use ``WriteableUser`` instead of
``CurrentUser``.

S2-DEV-016-READ-ONLY-FLAG-DB AC#5 (刻晴 r2 amend redline, 套路 PR #240).

Exit codes:
  0 - clean
  1 - violations found (CI must FAIL)

Allow-list:
  - logout_all   (auth.py) -- read-only user must be able to log out
  - bind_phone   (auth.py) -- new-device phone bind is auth/recovery

`# noqa` markers are DISALLOWED (would allow silent bypass; if a new
endpoint genuinely needs to opt out, edit the ALLOW set here in a follow-up
PR + ADR amend).

Run locally:

    cd ~/repo/YiLuAn-hutao && backend/.venv/bin/python3 backend/scripts/lint_writeable_user.py

CI runs the same command; non-zero exit fails the gate.
"""
from __future__ import annotations

import glob
import re
import sys

ALLOW = {"logout_all", "bind_phone"}


def find_violations():
    violations = []
    for fp in sorted(glob.glob("backend/app/api/v1/**/*.py", recursive=True)):
        src = open(fp).read()
        for m in re.finditer(
            r"@(?:[a-zA-Z_]+)\.(post|put|delete|patch)\b[^@]*?async def (\w+)\(([^)]+)\)",
            src,
            re.DOTALL,
        ):
            verb = m.group(1).upper()
            fn = m.group(2)
            sig = m.group(3)
            if fn in ALLOW:
                continue
            if "CurrentUser" in sig:
                # find line number
                line_no = src[: m.start()].count("\n") + 1
                violations.append((fp, line_no, verb, fn))
            # `# noqa` ban: if WriteableUser is missing AND any noqa appears
            # in the signature, flag separately so future devs cannot bypass.
            if "noqa" in sig and "WriteableUser" not in sig:
                line_no = src[: m.start()].count("\n") + 1
                violations.append((fp, line_no, verb, fn + " [noqa-bypass]"))
    return violations


def main():
    violations = find_violations()
    if not violations:
        print("[lint_writeable_user] OK: no violations.")
        return 0
    print(
        "[lint_writeable_user] FAIL: mutating endpoint(s) still using "
        "CurrentUser instead of WriteableUser:"
    )
    for fp, line, verb, fn in violations:
        rel = fp.replace("backend/app/api/v1/", "")
        print(f"  {fp}:{line}: {verb} {fn}  ->  use WriteableUser ({rel})")
    print()
    print(
        "Fix: import WriteableUser from app.dependencies and replace the "
        "CurrentUser annotation in the endpoint signature."
    )
    print("If you genuinely need an exemption, edit ALLOW in this script + "
          "open a follow-up ADR (see ADR-0053 §5 / S2-DEV-016 AC#5).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
