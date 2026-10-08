"""文本模型适配层的统一接口与错误类型。业务模块只依赖这里，替换服务不影响作曲引擎。"""

from __future__ import annotations

import json
import re
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.schemas.base import format_validation_error

T = TypeVar("T", bound=BaseModel)


class ProviderError(Exception):
    """模型调用失败。message 面向用户与日志，绝不包含密钥。"""

    def __init__(self, code: str, message: str, retryable: bool = False, details: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or []


class TextModelProvider(Protocol):
    model_id: str

    def complete_json(self, *, purpose: str, system: str, user: str, schema: type[T],
                      temperature: float = 0.8) -> T:
        """请求模型并返回通过 schema 校验的结构化结果；失败抛出 ProviderError。"""
        ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(text: str) -> object:
    """兼容模型在 JSON 外包裹代码块或说明文字的情况。"""
    cleaned = _FENCE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise ProviderError("MODEL_BAD_RESPONSE", "模型没有返回 JSON 内容", retryable=True) from None
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ProviderError("MODEL_BAD_RESPONSE", f"模型返回的 JSON 无法解析：{exc.msg}", retryable=True) from exc


def validate_payload(payload: object, schema: type[T]) -> T:
    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        details = format_validation_error(exc)
        raise ProviderError(
            "MODEL_BAD_RESPONSE", "模型返回的数据不符合要求的格式", retryable=True, details=details
        ) from exc
