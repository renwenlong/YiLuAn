from typing import Any

from fastapi import HTTPException, status


def _build_detail(detail: str, error_code: str | None) -> Any:
    """Return either a plain string (legacy) or a dict with ``error_code``.

    The frontend dispatchers parse both shapes:
    - ``{"detail": "xxx"}`` (legacy string form, still accepted)
    - ``{"detail": {"error_code": "PHONE_REQUIRED", "message": "xxx"}}``
    """
    if error_code is None:
        return detail
    return {"error_code": error_code, "message": detail}


class AppException(HTTPException):
    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        error_code: str | None = None,
    ):
        super().__init__(status_code=status_code, detail=_build_detail(detail, error_code))
        self.error_code = error_code
        self.message = detail


class NotFoundException(AppException):
    def __init__(self, detail: str = "Resource not found", *, error_code: str | None = None):
        super().__init__(status.HTTP_404_NOT_FOUND, detail, error_code=error_code)


class UnauthorizedException(AppException):
    def __init__(self, detail: str = "Not authenticated", *, error_code: str | None = None):
        super().__init__(status.HTTP_401_UNAUTHORIZED, detail, error_code=error_code)


class ForbiddenException(AppException):
    def __init__(self, detail: str = "Permission denied", *, error_code: str | None = None):
        super().__init__(status.HTTP_403_FORBIDDEN, detail, error_code=error_code)


class BadRequestException(AppException):
    def __init__(self, detail: str = "Bad request", *, error_code: str | None = None):
        super().__init__(status.HTTP_400_BAD_REQUEST, detail, error_code=error_code)


class ConflictException(AppException):
    def __init__(self, detail: str = "Conflict", *, error_code: str | None = None):
        super().__init__(status.HTTP_409_CONFLICT, detail, error_code=error_code)


class TooManyRequestsException(AppException):
    def __init__(
        self,
        detail: str = "Too many requests",
        retry_after: int | None = None,
        *,
        error_code: str | None = None,
    ):
        super().__init__(status.HTTP_429_TOO_MANY_REQUESTS, detail, error_code=error_code)
        self.retry_after = retry_after


class NotExpirableOrderError(AppException):
    """Raised when an order cannot be expired (e.g. payment already succeeded)."""

    def __init__(self, detail: str = "Order cannot be expired", *, error_code: str | None = None):
        super().__init__(status.HTTP_409_CONFLICT, detail, error_code=error_code)
