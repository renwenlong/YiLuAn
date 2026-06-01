"""Temporary QA probe for S2-OPS-004 acceptance #3.

This test is intentionally failing. It validates that backend path changes still
run Backend Tests and block merge when backend is broken.
"""


def test_intentional_backend_failure_for_ci_paths_gate() -> None:
    assert False, "S2-OPS-004 QA probe: backend gate must fail and block merge"
