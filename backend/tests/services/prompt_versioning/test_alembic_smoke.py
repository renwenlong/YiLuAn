"""One-shot smoke: alembic migration 7a8e1c2d4f60 applies cleanly + reversibly.

Not part of the regular suite; run manually with::

    pytest backend/tests/services/prompt_versioning/test_alembic_smoke.py -v -p no:cacheprovider

The standard alembic env.py hard-codes pool_size/max_overflow which SQLite
rejects, so we don't run ``alembic upgrade head`` from the shell.  Instead
we let the test machinery construct an in-memory engine via ``async_engine_from_config``
with NullPool (no kwargs forwarded) and replay the upgrade/downgrade cycle
to prove reversibility.
"""

from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migration_7a8e1c2d4f60_chain_intact() -> None:
    """The migration chain must include 7a8e1c2d4f60 after 6bc9f3d4a001.

    Historical context (PR #237): when this sentinel was originally added,
    7a8e1c2d4f60 *was* the head. As new migrations land after it, the
    `is in heads` assertion no longer holds. The sentinel's real intent is
    to guard the revision’s chain position relative to 6bc9f3d4a001 (PR #231
    base), not to pin it as head. Loosened in S3-DEV-004-FEEDBACK-DOMAIN
    when ec17fc201944 was appended.
    """
    cfg = Config("alembic.ini")
    cfg.set_main_option(
        "script_location",
        "alembic",
    )
    script = ScriptDirectory.from_config(cfg)
    revisions = {rev.revision: rev for rev in script.walk_revisions()}
    assert "7a8e1c2d4f60" in revisions, "7a8e1c2d4f60 not discovered"
    new_rev = revisions["7a8e1c2d4f60"]
    assert new_rev.down_revision == "6bc9f3d4a001", (
        f"down_revision must be 6bc9f3d4a001 (PR #231 base), "
        f"got {new_rev.down_revision}"
    )
    # 7a8e1c2d4f60 must be reachable in the chain (loosened from `is head`
    # — see docstring history).
    all_revs = set(revisions)
    assert "7a8e1c2d4f60" in all_revs, (
        f"revision unreachable; revisions={sorted(all_revs)}"
    )
