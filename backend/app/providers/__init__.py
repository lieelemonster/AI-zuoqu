"""按后端配置选择文本模型服务。密钥只从环境变量读取，不写入数据库、任务文件或接口响应。"""

from app.providers.base import ProviderError, TextModelProvider
from app.providers.mock import MockProvider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.settings import settings


def get_provider() -> TextModelProvider:
    provider = settings.model_provider.strip().lower()
    if provider == "mock":
        return MockProvider()
    if provider in ("", "openai_compatible"):
        return OpenAICompatibleProvider(
            api_url=settings.model_api_url,
            api_key=settings.model_api_key,
            model=settings.model_name,
            timeout_seconds=settings.model_timeout_seconds,
            json_mode=settings.model_json_mode,
        )
    raise ProviderError("MODEL_NOT_CONFIGURED", f"不支持的 MODEL_PROVIDER：{settings.model_provider}")


__all__ = ["ProviderError", "TextModelProvider", "get_provider"]
