from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse

from app.core.security import create_access_token, create_refresh_token
from app.dependencies import CurrentUser, DBSession
from app.schemas.auth import TokenResponse, UserResponse
from app.schemas.user import AvatarUploadResponse, SwitchRoleRequest, UpdateUserRequest
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


@router.post("/me/switch-role", response_model=TokenResponse)
async def switch_role(
    body: SwitchRoleRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = UserService(session)
    user = await service.switch_role(current_user, body.role)
    token_data = {
        "sub": str(user.id),
        "role": user.role.value if user.role else None,
        "roles": user.get_roles(),
    }
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


@router.delete("/me")
async def delete_account(
    current_user: CurrentUser,
    session: DBSession,
):
    service = UserService(session)
    await service.delete_account(current_user)
    return JSONResponse(
        status_code=200,
        content={"message": "Account deleted successfully"},
    )
