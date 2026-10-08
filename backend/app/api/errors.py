"""接口统一错误格式：{"error": {"code", "message", "retryable", "fields"}}。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.providers.base import ProviderError
from app.schemas.base import format_error_list

_PROVIDER_STATUS = {
    "MODEL_NOT_CONFIGURED": 503,
    "MODEL_AUTH_FAILED": 502,
    "MODEL_TIMEOUT": 504,
    "MODEL_RATE_LIMITED": 503,
    "MODEL_UNAVAILABLE": 503,
    "MODEL_REQUEST_REJECTED": 502,
    "MODEL_BAD_RESPONSE": 502,
}


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False,
                 fields: list[str] | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.retryable = status, code, message, retryable
        self.fields = fields or []


def error_body(code: str, message: str, retryable: bool = False, fields: list[str] | None = None) -> dict:
    return {"error": {"code": code, "message": message, "retryable": retryable, "fields": fields or []}}


def _field_errors(errors) -> list[str]:
    return format_error_list(errors, skip_prefix=("body",))


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(error_body(exc.code, exc.message, exc.retryable, exc.fields), status_code=exc.status)

    @app.exception_handler(ProviderError)
    async def _provider_error(_: Request, exc: ProviderError):
        status = _PROVIDER_STATUS.get(exc.code, 502)
        return JSONResponse(error_body(exc.code, exc.message, exc.retryable, exc.details), status_code=status)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        fields = _field_errors(exc.errors())
        return JSONResponse(error_body("INVALID_INPUT", "请求内容不完整或格式不正确", False, fields), status_code=422)

    @app.exception_handler(ValidationError)
    async def _model_validation_error(_: Request, exc: ValidationError):
        fields = _field_errors(exc.errors())
        return JSONResponse(error_body("INVALID_INPUT", "请求内容不完整或格式不正确", False, fields), status_code=422)
