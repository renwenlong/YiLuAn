"""S3-DEV-003-PRECHECK-BACKEND c1 add companion_profiles.verification_completed_at

ADR-0046 §3.5 + 设计 ``docs/design/S3-trust-precheck-ui.md`` §3.2 +
魈 14:10Z 拍板.

# Why a new column instead of reusing ``certified_at``

``certified_at`` = cert issuance date from the credential authority
(external semantic). ``verification_completed_at`` = the moment admin
``approve_companion`` flips ``verification_status`` from ``pending`` to
``verified`` (internal semantic). Reusing ``certified_at`` would let
the OrderPrecheckSummaryView ``companion_cert_verified_at`` field
silently shift semantic if cert reissuance ever happens, so we keep
them physically distinct.

# Backfill posture

NULL is allowed; historical verified rows do not get backfilled. The
OrderPrecheckSummaryView surfaces NULL verbatim, front-end falls back
to ``certified_at`` per PRD §F4 文案规范 (handled outside this
migration).

Revision ID: fc921567741d
Revises: ec17fc201944
Create Date: 2026-06-10 14:15:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fc921567741d"
down_revision: Union[str, None] = "ec17fc201944"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companion_profiles",
        sa.Column(
            "verification_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("companion_profiles", "verification_completed_at")
