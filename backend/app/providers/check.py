"""文本模型检查：示例请求返回结构化数据；错误密钥与超时得到明确错误；输出中不含密钥。"""

import httpx
from pydantic import Field

from app.providers import ProviderError, get_provider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.schemas.base import ApiModel
from app.settings import settings

SYSTEM = "你是中文歌词助手。只输出 JSON 对象，不要输出其他文字。"
USER = '为主题“夏夜”给出一个歌名和 3 个意象关键词，格式：{"title": "歌名", "keywords": ["词1", "词2", "词3"]}'


class ExampleResult(ApiModel):
    title: str = Field(min_length=1, max_length=30)
    keywords: list[str] = Field(min_length=2, max_length=6)


def _request(provider, label: str) -> bool:
    try:
        result = provider.complete_json(purpose="example", system=SYSTEM, user=USER, schema=ExampleResult)
    except ProviderError as exc:
        print(f"  {label}：[{exc.code}] {exc.message}")
        return False
    print(f"  {label}：返回结构化数据 {result.to_json_dict()}")
    return True


def _expect_error(label: str, provider_factory, expected: str) -> bool:
    try:
        provider_factory().complete_json(purpose="example", system=SYSTEM, user=USER, schema=ExampleResult)
    except ProviderError as exc:
        leaked = settings.model_api_key and settings.model_api_key in exc.message
        mark = "✅" if exc.code == expected and not leaked else "❌"
        print(f"  {mark} {label}：[{exc.code}] {exc.message}")
        return exc.code == expected and not leaked
    print(f"  ❌ {label}：没有报错")
    return False


def _fake(status: int | None):
    def handler(request: httpx.Request) -> httpx.Response:
        if status is None:
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(status, json={"error": {"message": "invalid api key"}})
    return httpx.MockTransport(handler)


def main() -> int:
    provider_name = settings.model_provider or "openai_compatible"
    key_state = "已配置" if settings.model_api_key else "未配置"
    print(f"当前配置：MODEL_PROVIDER={provider_name}，MODEL_API_URL={settings.model_api_url or '（空）'}，"
          f"MODEL_NAME={settings.model_name or '（空）'}，MODEL_API_KEY {key_state}（不显示内容）\n")

    print("1. 示例请求")
    try:
        provider = get_provider()
    except ProviderError as exc:
        print(f"  [{exc.code}] {exc.message}")
        provider = None
    ok = _request(provider, f"{provider.model_id}") if provider else False

    print("\n2. 错误处理")
    real = provider_name == "openai_compatible" and settings.model_api_url and settings.model_name
    if real:
        errors_ok = _expect_error("错误密钥（真实服务）", lambda: OpenAICompatibleProvider(
            api_url=settings.model_api_url, api_key="sk-invalid-key-for-check", model=settings.model_name,
            timeout_seconds=30), "MODEL_AUTH_FAILED")
        errors_ok &= _expect_error("超时（真实服务，超时设为 0.001 秒）", lambda: OpenAICompatibleProvider(
            api_url=settings.model_api_url, api_key=settings.model_api_key or "x", model=settings.model_name,
            timeout_seconds=0.001), "MODEL_TIMEOUT")
    else:
        print("  （未配置真实服务，以下用本地模拟的服务响应演示错误转换）")
        fake = dict(api_url="https://example.invalid/v1", api_key="sk-local-fake", model="fake-model", timeout_seconds=5)
        errors_ok = _expect_error("错误密钥（模拟 HTTP 401）",
                                  lambda: OpenAICompatibleProvider(**fake, transport=_fake(401)), "MODEL_AUTH_FAILED")
        errors_ok &= _expect_error("超时（模拟读取超时）",
                                   lambda: OpenAICompatibleProvider(**fake, transport=_fake(None)), "MODEL_TIMEOUT")

    print("\n" + ("全部检查符合预期。" if ok and errors_ok else
                  "示例请求未成功：请在 .env 配置 MODEL_API_URL、MODEL_API_KEY、MODEL_NAME，"
                  "或设置 MODEL_PROVIDER=mock 使用离线演示模型。" if errors_ok else "错误处理检查失败。"))
    return 0 if ok and errors_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
