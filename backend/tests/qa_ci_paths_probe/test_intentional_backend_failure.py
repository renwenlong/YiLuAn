"""Temporary QA probe for S2-OPS-004 acceptance #3 (vs protected main).

Intentionally failing backend test. Validates that on the PROTECTED main branch,
a red required check (Backend Tests) makes the PR BLOCKED / not mergeable.
"""


def test_intentional_backend_failure_for_ci_paths_gate() -> None:
    assert False, "S2-OPS-004 QA probe: backend gate must block merge on protected main"
