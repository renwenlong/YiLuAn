from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BadRequestException, NotFoundException
from app.models.user import User, UserRole
from app.repositories.user import UserRepository
from app.schemas.user import UpdateUserRequest


class UserService:
    def __init__(self, session: AsyncSession):
        self.user_repo = UserRepository(session)

    async def get_user_by_id(self, user_id: UUID) -> User:
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundException("User not found")
        return user

    async def update_user(self, user: User, data: UpdateUserRequest) -> User:
        update_data = data.model_dump(exclude_unset=True)

        if "role" in update_data and update_data["role"] is not None:
            if user.role is not None:
                raise BadRequestException("Role cannot be changed once set")
            update_data["role"] = UserRole(update_data["role"])

        if not update_data:
            return user

        return await self.user_repo.update(user, update_data)
