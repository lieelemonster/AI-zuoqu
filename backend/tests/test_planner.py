import pytest

from app.lyrics.parser import parse_lyrics
from app.planner.check import LYRICS, ScriptedProvider, _ai_output
from app.planner.planner import build_prompts, plan_music
from app.presets import default_plan, load_presets, plan_errors
from app.providers import ProviderError
from app.providers.mock import MockProvider
from app.schemas.input import CreativeInput

PARSED = parse_lyrics(LYRICS)
INPUT = CreativeInput(theme_id="love", emotion_id="sweet", style_id="pop")


class FailingProvider:
    model_id = "failing"

    def __init__(self, code):
        self.code, self.calls = code, 0

    def complete_json(self, **_):
        self.calls += 1
        raise ProviderError(self.code, "失败")


def test_valid_ai_plan_is_used_with_our_seed():
    plan, record = plan_music(INPUT, PARSED, ScriptedProvider(_ai_output(bpm=104)), seed=42)
    assert record.source == "ai" and plan.bpm == 104 and plan.seed == 42
    assert plan.sections[2].chord_pattern_id == "pop_chorus_b"


@pytest.mark.parametrize("change", [
    {"chordPatternId": "jazz_ii_v_i"},
    {"rhythmPatternId": "pop_hook"},
])
def test_invalid_template_is_repaired_once(change):
    bad = _ai_output()
    bad["sections"][1].update(change)
    provider = ScriptedProvider(bad, _ai_output())
    plan, record = plan_music(INPUT, PARSED, provider, seed=1)
    assert record.source == "ai_repaired" and provider.calls == 2
    assert record.attempts[0].errors and not record.attempts[1].errors
    assert "存在以下问题" in provider.last_user


@pytest.mark.parametrize("bad", [
    _ai_output(bpm=180),
    _ai_output(mode="dorian"),
    _ai_output(melodyRange=[60, 66]),
    _ai_output(sections=[{"type": "verse", "bars": 8, "chordPatternId": "pop_verse_a",
                          "rhythmPatternId": "pop_verse"}]),
])
def test_persistently_invalid_plan_falls_back_to_default(bad):
    provider = ScriptedProvider(bad)
    plan, record = plan_music(INPUT, PARSED, provider, seed=3)
    assert record.source == "default" and provider.calls == 2 and record.fallback_reason
    assert plan == default_plan("pop", "sweet", 3)


@pytest.mark.parametrize("code", ["MODEL_TIMEOUT", "MODEL_AUTH_FAILED", "MODEL_NOT_CONFIGURED"])
def test_provider_failure_falls_back_without_repair(code):
    provider = FailingProvider(code)
    plan, record = plan_music(INPUT, PARSED, provider, seed=3)
    assert record.source == "default" and provider.calls == 1 and code in record.fallback_reason
    assert not plan_errors(plan, "pop")


def test_no_provider_uses_default():
    plan, record = plan_music(INPUT, PARSED, None, seed=3)
    assert record.source == "default" and record.model_id == "none"


@pytest.mark.parametrize("style", [s.id for s in load_presets().styles])
def test_mock_plan_is_valid_for_every_style_with_bridge(style):
    lyrics = LYRICS + "\n[桥段]\n风停了\n我还在\n[副歌]\n就这样走下去\n心里有光"
    data = CreativeInput(theme_id="dream", emotion_id="hopeful", style_id=style)
    plan, record = plan_music(data, parse_lyrics(lyrics), MockProvider(), seed=5)
    assert record.source == "ai", record.attempts
    assert [s.type for s in plan.sections] == ["intro", "verse", "chorus", "bridge", "chorus", "outro"]


def test_prompt_lists_only_style_templates_and_structure():
    system, user = build_prompts(INPUT, PARSED)
    assert "钢琴主旋律与简单伴奏" in system and "output_schema" in system
    assert "pop_chorus_b" in user and "rock_" not in user
    assert "晚风吹过街角" in user
