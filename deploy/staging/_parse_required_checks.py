#!/usr/bin/env python3
"""Parse a GitHub check-runs API response and report required-check status.

Reads the check-runs JSON (``{"check_runs": [...]}`` shape) on stdin and
takes the required check names as argv. For each required name it finds
the latest run (by ``started_at``) and prints ``NAME\\tCONCLUSION`` to
stdout. A required check with no run is reported as ``MISSING``.

Kept import-light and side-effect free so it is trivial to unit test and
so it has no stdin-vs-here-doc conflict when called from bash.

Exit codes:
    0  parsed OK (status lines on stdout; caller decides pass/fail)
    3  JSON parse error
"""
import json
import sys


def main() -> int:
    required = sys.argv[1:]
    try:
        data = json.load(sys.stdin)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("PARSE_ERROR: %s\n" % exc)
        return 3

    runs = data.get("check_runs", []) if isinstance(data, dict) else []

    latest = {}
    for run in runs:
        if not isinstance(run, dict):
            continue
        name = run.get("name")
        if name is None:
            continue
        started = run.get("started_at") or ""
        prev = latest.get(name)
        # keep the latest run by started_at (ISO-8601 lexical compare is fine)
        if prev is None or started >= prev[0]:
            conclusion = run.get("conclusion") or run.get("status") or "unknown"
            latest[name] = (started, conclusion)

    for name in required:
        entry = latest.get(name)
        conclusion = entry[1] if entry is not None else "MISSING"
        sys.stdout.write("%s\t%s\n" % (name, conclusion))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
