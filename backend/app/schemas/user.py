from pydantic import BaseModel, field_validator


class UpdateUserRequest(BaseModel):
    role: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str | None) -> str | None:
        if v is not None and v not in ("patient", "companion"):
            raise ValueError("Role must be 'patient' or 'companion'")
        return v
