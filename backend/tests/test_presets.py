import pytest

from app.presets import (
    UnknownPresetError,
    default_plan,
    get_style,
    load_presets,
    load_styles,
    plan_errors,
    validate_creative_input,
)
from app.schemas import CreativeInput

PRD_THEMES = ["爱情", "友情", "亲情", "青春校园", "成长追梦", "治愈鼓励", "回忆怀念", "故乡", "旅行", "日常生活"]
PRD_EMOTIONS = ["甜蜜", "快乐", "悲伤", "思念", "温暖", "轻松", "孤独", "怀旧", "热血", "充满希望"]
PRD_STYLES = ["流行", "民谣", "国风", "摇滚", "R&B", "电子", "说唱"]


def test_presets_match_prd():
    presets = load_presets()
    assert [o.name for o in presets.themes] == PRD_THEMES
    assert [o.name for o in presets.emotions] == PRD_EMOTIONS
    assert [o.name for o in presets.styles] == PRD_STYLES


@pytest.mark.parametrize("style_id", [o.id for o in load_presets().styles])
@pytest.mark.parametrize("emotion_id", [o.id for o in load_presets().emotions])
def test_every_default_plan_is_valid(style_id, emotion_id):
    plan = default_plan(style_id, emotion_id, seed=7)
    assert plan_errors(plan, style_id) == []
    bars = sum(s.bars for s in plan.sections)
    assert 45 <= bars * 4 * 60 / plan.bpm + 2 <= 75


def test_emotion_changes_mode_and_tempo():
    happy, sad = default_plan("pop", "happy", 1), default_plan("pop", "sad", 1)
    assert (happy.mode, sad.mode) == ("major", "minor")
    assert happy.bpm > sad.bpm


def test_unknown_ids_rejected():
    with pytest.raises(UnknownPresetError, match="风格"):
        get_style("jazz")
    with pytest.raises(UnknownPresetError, match="主题"):
        validate_creative_input(CreativeInput(theme_id="war", emotion_id="sad", style_id="pop"))
    validate_creative_input(CreativeInput(theme_id="love", emotion_id="sad", style_id="pop"))


def test_plan_with_unknown_template_reported():
    plan = default_plan("folk", "warm", 1)
    plan.sections[1].chord_pattern_id = "pop_chorus_a"
    plan.sections[2].rhythm_pattern_id = "folk_ending"
    errors = plan_errors(plan, "folk")
    assert any("没有和弦模板 pop_chorus_a" in e for e in errors)
    assert any("不适用于 chorus" in e for e in errors)


def test_rap_is_rhythm_first():
    assert get_style("rap").rhythmic_melody is True
    assert all(not s.rhythmic_melody for s in load_styles().styles if s.style_id != "rap")
