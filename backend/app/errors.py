from fastapi import Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    def __init__(
        self,
        detail: str,
        code: str,
        status_code: int = 400,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.status_code = status_code
        self.headers = headers or {}


async def domain_error_handler(
    _request: Request, exc: DomainError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
        headers=exc.headers,
    )
