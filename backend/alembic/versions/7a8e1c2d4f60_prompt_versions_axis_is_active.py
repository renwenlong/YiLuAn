"""prompt_versions ADR §5.2 schema completion (axis/is_active/activated_at/max_tokens)

S3-DEV-002-PROMPT-VERSIONING AC#1 schema completion + 启动校验前置.

ADR-0048 §5.2 designed ``prompt_versions`` with 4 extra fields that were
omitted in the initial migration ``6bc9f3d4a001`` (S3-DEV-002-PREP-PACKAGE-MIGRATION):

  - ``axis``         VARCHAR(32) NOT NULL — BudgetAxis enum value (``s3_prep`` / ``s2_summary``)
  - ``is_active``    BOOLEAN NOT NULL DEFAULT FALSE — single-truth active flag
  - ``activated_at`` TIMESTAMPTZ NULL — observability for activation history
  - ``max_tokens``   INTEGER NULL — model max-output cap (per ADR §5.2)

Partial unique index ``ix_prompt_versions_active_per_axis`` enforces
"at most one active prompt per axis" — required by AC#3 startup validator
which expects ``one_or_none()`` lookup for ``(axis, is_active=True)``.

The pre-existing ``uq_prompt_versions_version`` (single-column on ``version``)
is replaced with a multi-column ``(axis, version)`` unique to mirror ADR §5.2's
``UNIQUE (axis, version)`` (so two axes can share semver e.g. v1.0.0).

Revision ID: 7a8e1c2d4f60
Revises: 6bc9f3d4a001
Create Date: 2026-06-09 16:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a8e1c2d4f60"
down_revision: Union[str, None] = "6bc9f3d4a001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DEFAULT_AXIS = "s3_prep"


def upgrade() -> None:
    # ── 1. add 4 new columns ──────────────────────────────────────────────
    # ``axis`` is NOT NULL but server_default keeps existing rows valid
    # (only the initial S3 prep prompt version is plausibly in PR-227 era;
    # empty table on prod at migration time).  ADR §5.2 default = s3_prep.
    op.add_column(
        "prompt_versions",
        sa.Column(
            "axis",
            sa.String(length=32),
            nullable=False,
            server_default=_DEFAULT_AXIS,
        ),
    )
    op.add_column(
        "prompt_versions",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "prompt_versions",
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "prompt_versions",
        sa.Column(
            "max_tokens",
            sa.Integer(),
            nullable=True,
        ),
    )

    # ── 2. replace single-column unique with (axis, version) ──────────────
    # Old single-column unique disallows two axes sharing semver.
    op.drop_constraint(
        "uq_prompt_versions_version",
        "prompt_versions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_prompt_versions_axis_version",
        "prompt_versions",
        ["axis", "version"],
    )

    # ── 3. partial unique index: at most 1 active prompt per axis ─────────
    # AC#3 startup validator does ``filter_by(axis=..., is_active=True).one_or_none()``
    # which requires this uniqueness invariant at DB level (not application).
    # PG: partial index works.  SQLite: ``CREATE UNIQUE INDEX ... WHERE ...``
    # also supported since 3.8.  Both supported.
    op.create_index(
        "ix_prompt_versions_active_per_axis",
        "prompt_versions",
        ["axis"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
        sqlite_where=sa.text("is_active = 1"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prompt_versions_active_per_axis",
        table_name="prompt_versions",
    )
    op.drop_constraint(
        "uq_prompt_versions_axis_version",
        "prompt_versions",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_prompt_versions_version",
        "prompt_versions",
        ["version"],
    )
    op.drop_column("prompt_versions", "max_tokens")
    op.drop_column("prompt_versions", "activated_at")
    op.drop_column("prompt_versions", "is_active")
    op.drop_column("prompt_versions", "axis")
