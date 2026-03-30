from fastapi import APIRouter, UploadFile

from app.dependencies import CurrentUser, DBSession
from app.schemas.auth import UserResponse
from app.schemas.user import AvatarUploadResponse, UpdateUserRequest
from app.services.upload import UploadService
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


@router.post("/me/avatar", response_model=AvatarUploadResponse)
async def upload_avatar(
    file: UploadFile,
    current_user: CurrentUser,
    session: DBSession,
):
    upload_service = UploadService()
    avatar_url = await upload_service.upload_avatar(current_user.id, file)
    user_service = UserService(session)
    await user_service.update_user(
        current_user, UpdateUserRequest(avatar_url=avatar_url)
    )
    return AvatarUploadResponse(avatar_url=avatar_url)
