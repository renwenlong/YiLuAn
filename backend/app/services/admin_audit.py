"""
AdminAuditService — companion audit business logic (B1).
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models.admin_audit_log import AdminAuditLog
from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.user import User


class AdminAuditService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_pending_companions(
        self, page: int = 1, page_size: int = 20
    ) -> dict:
        base = select(CompanionProfile).where(
            CompanionProfile.verification_status == VerificationStatus.pending
        )
        total_result = await self.session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = total_result.scalar_one()

        skip = (page - 1) * page_size
        items_result = await self.session.execute(
            base.order_by(CompanionProfile.created_at.asc())
            .offset(skip)
            .limit(page_size)
        )
        items = items_result.scalars().all()
        return {
            "items": [
                {
                    "id": str(p.id),
                    "real_name": p.real_name,
                    "id_number": p.id_number,
                    "certifications": p.certifications,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def approve_companion(
        self, companion_id: UUID, operator_id: str
    ) -> CompanionProfile:
        profile = await self.session.get(CompanionProfile, companion_id)
        if profile is None:
            raise NotFoundException("Companion profile not found")
        if profile.verification_status != VerificationStatus.pending:
            raise ConflictException(
                f"Profile status is '{profile.verification_status.value}', expected 'pending'"
            )

        # 上架（verified）前兜底校验：陪诊师必须已绑定手机号，否则无法被联系
        owner = await self.session.get(User, profile.user_id)
        if owner is None or not owner.phone:
            raise BadRequestException(
                "陪诊师未绑定手机号，无法上架。请通知陪诊师补全手机号后再审核。",
                error_code=error_codes.PHONE_REQUIRED,
            )

        profile.verification_status = VerificationStatus.verified
        profile.updated_at = datetime.now(timezone.utc)

        log = AdminAuditLog(
            target_type="companion",
            target_id=companion_id,
            action="approve",
            operator=operator_id,
        )
        self.session.add(log)
        await self.session.flush()
        return profile

    async def reject_companion(
        self, companion_id: UUID, operator_id: str, reason: str
    ) -> CompanionProfile:
        profile = await self.session.get(CompanionProfile, companion_id)
        if profile is None:
            raise NotFoundException("Companion profile not found")
        if profile.verification_status != VerificationStatus.pending:
            raise ConflictException(
                f"Profile status is '{profile.verification_status.value}', expected 'pending'"
            )

        profile.verification_status = VerificationStatus.rejected
        profile.updated_at = datetime.now(timezone.utc)

        log = AdminAuditLog(
            target_type="companion",
            target_id=companion_id,
            action="reject",
            operator=operator_id,
            reason=reason,
        )
        self.session.add(log)
        await self.session.flush()
        return profile

    async def certify_companion(
        self,
        companion_id: UUID,
        operator_id: str,
        certification_type: str,
        certification_no: str,
        certification_image_url: str,
    ) -> CompanionProfile:
        """F-01: Set companion certification (type/no/image) and stamp certified_at."""
        profile = await self.session.get(CompanionProfile, companion_id)
        if profile is None:
            raise NotFoundException("Companion profile not found")

        profile.certification_type = certification_type
        profile.certification_no = certification_no
        profile.certification_image_url = certification_image_url
        profile.certified_at = datetime.now(timezone.utc)
        profile.updated_at = datetime.now(timezone.utc)

        log = AdminAuditLog(
            target_type="companion",
            target_id=companion_id,
            action="certify",
            operator=operator_id,
            reason=f"{certification_type}:{certification_no}",
        )
        self.session.add(log)
        await self.session.flush()
        await self.session.refresh(profile)
        return profile
