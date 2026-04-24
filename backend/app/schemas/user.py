from pydantic import BaseModel, Field, field_validator


class UpdateUserRequest(BaseModel):
    role: str | None = Field(None, description="切换活跃角色：patient / companion", examples=["patient"])
    display_name: str | None = Field(None, description="昵称", examples=["小明"])
    avatar_url: str | None = Field(None, description="头像 URL")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str | None) -> str | None:
        if v is not None and v not in ("patient", "companion"):
            raise ValueError("Role must be 'patient' or 'companion'")
        return v


class AvatarUploadResponse(BaseModel):
    avatar_url: str = Field(..., description="新头像的访问 URL", examples=["https://cdn.example.com/avatars/u1.jpg"])


class SwitchRoleRequest(BaseModel):
    role: str = Field(..., description="目标角色：patient / companion", examples=["companion"])

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("patient", "companion"):
            raise ValueError("Role must be 'patient' or 'companion'")
        return v
