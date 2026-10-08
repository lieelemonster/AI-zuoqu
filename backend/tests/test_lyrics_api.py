import pytest
from fastapi.testclient import TestClient

from app.lyrics.generator import build_prompts
from app.lyrics.parser import parse_lyrics
from app.main import app
from app.presets import load_presets
from app.providers import ProviderError, get_provider
from app.providers.base import validate_payload
from app.providers.mock import MockProvider
from app.schemas.input import CreativeInput

GOOD = "[主歌]\n晚风吹过街角\n你笑着回头\n路灯一盏一盏\n照亮我们的路\n[副歌]\n就这样走下去\n不怕夜太长\n就这样走下去\n心里有光"


class FakeProvider:
    model_id = "fake"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def complete_json(self, *, purpose, system, user, schema, temperature=0.8):
        self.calls += 1
        response = self.responses[min(self.calls, len(self.responses)) - 1]
        if isinstance(response, Exception):
            raise response
        return validate_payload(response, schema)


def payload(text=GOOD, approaches=("story", "emotion", "imagery")):
    return {"variants": [{"approach": a, "title": "歌名", "text": text} for a in approaches]}


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def use(provider):
    app.dependency_overrides[get_provider] = lambda: provider
    return provider


BODY = {"themeId": "love", "emotionId": "sweet", "styleId": "pop", "story": ""}


@pytest.mark.parametrize("style", [s.id for s in load_presets().styles])
def test_mock_returns_three_composable_variants(client, style):
    use(MockProvider())
    response = client.post("/api/lyrics", json={**BODY, "styleId": style})
    assert response.status_code == 200
    data = response.json()
    assert [v["approach"] for v in data["variants"]] == ["story", "emotion", "imagery"]
    assert data["modelId"] == "mock" and data["promptVersion"]
    for variant in data["variants"]:
        parsed = parse_lyrics(variant["text"])
        assert parsed.ok and {s.type for s in parsed.sections} == {"verse", "chorus"}


def test_prompt_contains_names_and_story():
    system, user = build_prompts(CreativeInput(theme_id="hometown", emotion_id="nostalgic", style_id="rap",
                                               story="外婆家门口的老槐树"))
    assert "story" in system and "imagery" in system and "押韵" in system
    assert "故乡" in user and "外婆家门口的老槐树" in user


def test_bad_structure_is_retried_once(client):
    provider = use(FakeProvider(payload(text="只有一行没有段落标题的歌词内容"), payload()))
    response = client.post("/api/lyrics", json=BODY)
    assert response.status_code == 200 and provider.calls == 2


def test_persistently_bad_output_returns_retryable_error(client):
    provider = use(FakeProvider(payload(approaches=("story", "story", "emotion"))))
    response = client.post("/api/lyrics", json=BODY)
    error = response.json()["error"]
    assert response.status_code == 502 and provider.calls == 2
    assert error["code"] == "LYRICS_INVALID" and error["retryable"] and error["fields"]


def test_lyrics_too_long_for_one_minute_are_rejected(client):
    long_text = "[主歌]\n" + "\n".join(["我们一起走过春夏秋冬的街"] * 14) + "\n[副歌]\n" + "\n".join(["永远记得你"] * 10)
    use(FakeProvider(payload(text=long_text)))
    error = client.post("/api/lyrics", json=BODY).json()["error"]
    assert error["code"] == "LYRICS_INVALID" and any("超过 75 秒" in f for f in error["fields"])


@pytest.mark.parametrize(("code", "status"), [("MODEL_TIMEOUT", 504), ("MODEL_AUTH_FAILED", 502),
                                              ("MODEL_NOT_CONFIGURED", 503)])
def test_provider_errors_are_not_retried_internally(client, code, status):
    provider = use(FakeProvider(ProviderError(code, "失败", retryable=code == "MODEL_TIMEOUT")))
    response = client.post("/api/lyrics", json=BODY)
    assert response.status_code == status and provider.calls == 1
    assert response.json()["error"]["code"] == code


def test_invalid_input(client):
    use(MockProvider())
    response = client.post("/api/lyrics", json={**BODY, "themeId": "unknown"})
    assert response.status_code == 422 and "主题" in response.json()["error"]["message"]
    response = client.post("/api/lyrics", json={"themeId": "love"})
    assert any("styleId" in f for f in response.json()["error"]["fields"])
