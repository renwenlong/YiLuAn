from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse

from app.api.v1.openapi_meta import err
from app.core.security import create_access_token, create_refresh_token
from app.dependencies import CurrentUser, DBSession
from app.schemas.auth import TokenResponse, UserResponse
from app.schemas.user import AvatarUploadResponse, SwitchRoleRequest, UpdateUserRequest
from app.services.upload import UploadService
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserResponse,
    summary="获取当前登录用户信息",
    description="返回当前 JWT 对应用户的基本资料（id、手机号、昵称、头像、角色、可用角色集合）。",
    responses={**err(401, 500)},
)
async def get_me(current_user: CurrentUser):
    return current_user


@router.put(
    "/me",
    response_model=UserResponse,
    summary="更新当前用户基本资料",
    description="支持修改昵称、头像 URL、当前活跃角色。手机号不能通过本接口修改。",
    responses={**err(401, 422, 500)},
)
async def update_me(
    body: UpdateUserRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = UserService(session)
    return await service.update_user(current_user, body)


@router.post(
    "/me/avatar",
    response_model=AvatarUploadResponse,
    summary="上传头像",
    description=(
        "上传一张头像图片（multipart/form-data，字段名 `file`）。"
        "服务端保存到对象存储后，将 URL 写回用户资料并返回最终 URL。"
    ),
    responses={**err(401, 413, 415, 500)},
)
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


@router.post(
    "/me/switch-role",
    response_model=TokenResponse,
    summary="切换活跃角色",
    description=(
        "在 `patient` 与 `companion` 两个已开通的角色间切换，"
        "**返回新的 JWT 令牌对**（新令牌的 `role` claim 已更新）。"
    ),
    responses={**err(400, 401, 422, 500)},
)
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


@router.delete(
    "/me",
    summary="注销当前账户",
    description="**永久**删除当前用户账户及关联数据。操作不可恢复，请前端二次确认。",
    responses={
        200: {"content": {"application/json": {"example": {"message": "Account deleted successfully"}}}},
        **err(401, 500),
    },
)
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
