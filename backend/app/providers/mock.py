"""离线演示模型：仅在 MODEL_PROVIDER=mock 时使用，按用途返回固定规则生成的结构化数据。

它用于没有模型密钥时走通流程与自动测试；真实模型失败时不会自动改用它。
"""

from __future__ import annotations

from typing import Callable

from app.providers.base import ProviderError, T, validate_payload

MockHandler = Callable[[str, str], object]
_HANDLERS: dict[str, MockHandler] = {}


def register_mock(purpose: str) -> Callable[[MockHandler], MockHandler]:
    def decorator(handler: MockHandler) -> MockHandler:
        _HANDLERS[purpose] = handler
        return handler
    return decorator


@register_mock("example")
def _example(system: str, user: str) -> object:
    return {"title": "夏夜的风", "keywords": ["晚风", "星光", "单车"]}


class MockProvider:
    model_id = "mock"

    def complete_json(self, *, purpose: str, system: str, user: str, schema: type[T],
                      temperature: float = 0.8) -> T:
        handler = _HANDLERS.get(purpose)
        if handler is None:
            raise ProviderError("MODEL_NOT_CONFIGURED", f"离线演示模型不支持用途 {purpose}")
        return validate_payload(handler(system, user), schema)
