"""[F-03] Emergency service layer."""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.models.emergency import EmergencyContact, EmergencyEvent
from app.repositories.emergency import (
    EmergencyContactRepository,
    EmergencyEventRepository,
)
from app.schemas.emergency import (
    EmergencyContactCreate,
    EmergencyContactUpdate,
    EmergencyTriggerRequest,
)

MAX_EMERGENCY_CONTACTS = 3


class EmergencyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.contact_repo = EmergencyContactRepository(session)
        self.event_repo = EmergencyEventRepository(session)

    # ------------------------------------------------------------------
    # Contacts CRUD
    # ------------------------------------------------------------------
    async def list_contacts(self, user_id: UUID):
        return await self.contact_repo.list_by_user(user_id)

    async def create_contact(
        self, user_id: UUID, data: EmergencyContactCreate
    ) -> EmergencyContact:
        existing = await self.contact_repo.list_by_user(user_id)
        if len(existing) >= MAX_EMERGENCY_CONTACTS:
            raise ConflictException(
                f"最多可添加 {MAX_EMERGENCY_CONTACTS} 个紧急联系人",
                error_code="EMERGENCY_CONTACT_LIMIT",
            )
        contact = EmergencyContact(
            user_id=user_id,
            name=data.name,
            phone=data.phone,
            relationship=data.relationship,
        )
        return await self.contact_repo.create(contact)

    async def _get_owned_contact(
        self, user_id: UUID, contact_id: UUID
    ) -> EmergencyContact:
        contact = await self.contact_repo.get_by_id(contact_id)
        if contact is None:
            raise NotFoundException("联系人不存在")
        if contact.user_id != user_id:
            raise ForbiddenException("无权操作他人联系人")
        return contact

    async def update_contact(
        self, user_id: UUID, contact_id: UUID, data: EmergencyContactUpdate
    ) -> EmergencyContact:
        contact = await self._get_owned_contact(user_id, contact_id)
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return contact
        return await self.contact_repo.update(contact, update_data)

    async def delete_contact(self, user_id: UUID, contact_id: UUID) -> None:
        contact = await self._get_owned_contact(user_id, contact_id)
        await self.contact_repo.delete(contact)

    # ------------------------------------------------------------------
    # Trigger event
    # ------------------------------------------------------------------
    async def trigger_event(
        self, user_id: UUID, data: EmergencyTriggerRequest
    ) -> tuple[EmergencyEvent, str]:
        if not data.hotline and data.contact_id is None:
            raise BadRequestException(
                "必须指定 contact_id 或将 hotline 置为 true",
                error_code="EMERGENCY_TARGET_REQUIRED",
            )

        if data.hotline:
            phone = settings.emergency_hotline
            contact_type = "hotline"
        else:
            contact = await self._get_owned_contact(user_id, data.contact_id)  # type: ignore[arg-type]
            phone = contact.phone
            contact_type = "contact"

        event = EmergencyEvent(
            patient_id=user_id,
            order_id=data.order_id,
            contact_called=phone,
            contact_type=contact_type,
            location=data.location,
        )
        event = await self.event_repo.create(event)
        return event, phone
