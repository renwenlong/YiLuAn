from fastapi import APIRouter

from app.dependencies import CurrentUser, DBSession
from app.schemas.auth import UserResponse
from app.schemas.user import UpdateUserRequest
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser):
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_me(
    body: UpdateUserRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = UserService(session)
    return await service.update_user(current_user, body)
