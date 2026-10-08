"""OpenAI 兼容的 Chat Completions 接口（DeepSeek、通义千问兼容模式、Kimi、智谱、OpenAI 等）。"""

from __future__ import annotations

import logging

import httpx

from app.providers.base import ProviderError, T, extract_json, validate_payload

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider:
    def __init__(self, *, api_url: str, api_key: str, model: str, timeout_seconds: float,
                 json_mode: bool = True, transport: httpx.BaseTransport | None = None):
        if not api_url or not api_key or not model:
            missing = [name for name, value in (("MODEL_API_URL", api_url), ("MODEL_API_KEY", api_key),
                                                ("MODEL_NAME", model)) if not value]
            raise ProviderError("MODEL_NOT_CONFIGURED", f"文本模型未配置：请在后端 .env 中填写 {'、'.join(missing)}")
        url = api_url.rstrip("/")
        self.endpoint = url if url.endswith("/chat/completions") else f"{url}/chat/completions"
        self._api_key = api_key
        self.model_id = model
        self.timeout_seconds = timeout_seconds
        self.json_mode = json_mode
        self._transport = transport

    def _scrub(self, text: str) -> str:
        return text.replace(self._api_key, "***") if self._api_key else text

    def complete_json(self, *, purpose: str, system: str, user: str, schema: type[T],
                      temperature: float = 0.8) -> T:
        body = {
            "model": self.model_id,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
        }
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self._transport) as client:
                response = client.post(self.endpoint, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError("MODEL_TIMEOUT", f"文本模型超过 {self.timeout_seconds:g} 秒未响应，请稍后重试",
                                retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("MODEL_UNAVAILABLE", f"无法连接文本模型服务：{self._scrub(type(exc).__name__)}",
                                retryable=True) from exc

        status = response.status_code
        if status in (401, 403):
            raise ProviderError("MODEL_AUTH_FAILED", "文本模型密钥无效或无权限，请检查后端 .env 中的 MODEL_API_KEY")
        if status == 429:
            raise ProviderError("MODEL_RATE_LIMITED", "文本模型请求过于频繁或额度不足，请稍后重试", retryable=True)
        if status >= 500:
            raise ProviderError("MODEL_UNAVAILABLE", f"文本模型服务暂时不可用（HTTP {status}），请稍后重试",
                                retryable=True)
        if status >= 400:
            snippet = self._scrub(response.text[:200])
            raise ProviderError("MODEL_REQUEST_REJECTED", f"文本模型拒绝了请求（HTTP {status}）：{snippet}")

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("MODEL_BAD_RESPONSE", "文本模型返回的响应结构无法识别", retryable=True) from exc
        logger.info("模型调用完成 purpose=%s model=%s 字符数=%d", purpose, self.model_id, len(content or ""))
        return validate_payload(extract_json(content or ""), schema)
