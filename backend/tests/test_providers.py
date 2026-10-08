import json
from pathlib import Path

import httpx
import pytest

from app.providers import ProviderError
from app.providers.check import ExampleResult
from app.providers.mock import MockProvider
from app.providers.openai_compatible import OpenAICompatibleProvider

KEY = "sk-secret-test-key-123456"
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def provider(handler, **kwargs):
    options = dict(api_url="https://example.invalid/v1", api_key=KEY, model="m", timeout_seconds=5)
    options.update(kwargs)
    return OpenAICompatibleProvider(**options, transport=httpx.MockTransport(handler))


def reply(content: str):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    return handler


def call(p):
    return p.complete_json(purpose="example", system="s", user="u", schema=ExampleResult)


def test_structured_success_and_fenced_json():
    assert call(provider(reply('{"title": "夏夜", "keywords": ["风", "星"]}'))).title == "夏夜"
    fenced = '好的：\n```json\n{"title": "夏夜", "keywords": ["风", "星"]}\n```'
    assert call(provider(reply(fenced))).keywords == ["风", "星"]


@pytest.mark.parametrize(("status", "code", "retryable"), [
    (401, "MODEL_AUTH_FAILED", False), (403, "MODEL_AUTH_FAILED", False),
    (429, "MODEL_RATE_LIMITED", True), (502, "MODEL_UNAVAILABLE", True), (400, "MODEL_REQUEST_REJECTED", False),
])
def test_http_errors_are_mapped(status, code, retryable):
    p = provider(lambda r: httpx.Response(status, text=f"bad key {KEY}"))
    with pytest.raises(ProviderError) as info:
        call(p)
    assert (info.value.code, info.value.retryable) == (code, retryable)
    assert KEY not in info.value.message


def test_timeout_and_connection_errors():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderError) as info:
        call(provider(timeout))
    assert info.value.code == "MODEL_TIMEOUT" and info.value.retryable
    with pytest.raises(ProviderError) as info:
        call(provider(refused))
    assert info.value.code == "MODEL_UNAVAILABLE"


def test_bad_json_and_schema_errors_have_details():
    with pytest.raises(ProviderError) as info:
        call(provider(reply("抱歉我不能")))
    assert info.value.code == "MODEL_BAD_RESPONSE"
    with pytest.raises(ProviderError) as info:
        call(provider(reply('{"title": "夏夜", "keywords": ["风"]}')))
    assert info.value.code == "MODEL_BAD_RESPONSE"
    assert any(d.startswith("keywords") for d in info.value.details)


def test_missing_configuration_lists_fields():
    with pytest.raises(ProviderError) as info:
        OpenAICompatibleProvider(api_url="", api_key="", model="x", timeout_seconds=1)
    assert info.value.code == "MODEL_NOT_CONFIGURED"
    assert "MODEL_API_URL" in info.value.message and "MODEL_API_KEY" in info.value.message


def test_mock_provider_is_explicit():
    assert call(MockProvider()).title
    with pytest.raises(ProviderError):
        MockProvider().complete_json(purpose="unknown", system="", user="", schema=ExampleResult)


def test_frontend_never_references_model_key():
    for path in FRONTEND.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert "MODEL_API_KEY" not in text and "Authorization" not in text, path
