import uuid
from pathlib import Path

from fastapi import UploadFile

from app.exceptions import BadRequestException

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/jpg"}
MAX_SIZE = 5 * 1024 * 1024  # 5MB
STATIC_DIR = Path(__file__).parent.parent.parent / "static" / "avatars"


class UploadService:
    async def upload_avatar(self, user_id: uuid.UUID, file: UploadFile) -> str:
        if file.content_type not in ALLOWED_TYPES:
            raise BadRequestException(
                "Invalid file type. Only jpg/jpeg/png are allowed"
            )

        content = await file.read()
        if len(content) > MAX_SIZE:
            raise BadRequestException("File too large. Maximum size is 5MB")

        ext = file.filename.rsplit(".", 1)[-1] if file.filename else "jpg"
        filename = f"{user_id}_{uuid.uuid4().hex[:8]}.{ext}"

        STATIC_DIR.mkdir(parents=True, exist_ok=True)
        file_path = STATIC_DIR / filename
        file_path.write_bytes(content)

        return f"/static/avatars/{filename}"
