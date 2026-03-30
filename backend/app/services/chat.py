import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ForbiddenException, NotFoundException
from app.models.chat_message import ChatMessage, MessageType
from app.models.order import Order, OrderStatus
from app.models.user import User, UserRole
from app.repositories.chat_message import ChatMessageRepository
from app.repositories.order import OrderRepository
from app.schemas.chat import SendMessageRequest


class ChatService:
    def __init__(self, session: AsyncSession):
        self.chat_repo = ChatMessageRepository(session)
        self.order_repo = OrderRepository(session)
        self.session = session

    async def send_message(
        self, order_id: uuid.UUID, user: User, data: SendMessageRequest
    ) -> ChatMessage:
        order = await self._get_order_and_validate(order_id, user)

        message = ChatMessage(
            order_id=order_id,
            sender_id=user.id,
            type=MessageType(data.type),
            content=data.content,
        )
        return await self.chat_repo.create(message)

    async def list_messages(
        self,
        order_id: uuid.UUID,
        user: User,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list, int]:
        await self._get_order_and_validate(order_id, user)
        skip = (page - 1) * page_size
        return await self.chat_repo.list_by_order(
            order_id, skip=skip, limit=page_size
        )

    async def mark_read(self, order_id: uuid.UUID, user: User) -> int:
        await self._get_order_and_validate(order_id, user)
        return await self.chat_repo.mark_as_read(order_id, user.id)

    async def _get_order_and_validate(
        self, order_id: uuid.UUID, user: User
    ) -> Order:
        order = await self.order_repo.get_by_id(order_id)
        if order is None:
            raise NotFoundException("Order not found")

        is_patient = order.patient_id == user.id
        is_companion = order.companion_id == user.id
        if not is_patient and not is_companion:
            raise ForbiddenException("Not a participant of this order")

        return order
