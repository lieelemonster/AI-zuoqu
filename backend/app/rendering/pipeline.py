"""乐谱 → MIDI → WAV → MP3 → 成品检查。中间文件与成品放在同一个目录。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.presets import load_composition
from app.rendering.audio import WavInfo, render_wav
from app.rendering.encode import AudioCheck, check_final_audio, encode_mp3
from app.rendering.midi import write_midi
from app.schemas.score import Score


@dataclass(frozen=True)
class RenderResult:
    score_path: Path
    midi_path: Path
    wav: WavInfo
    mp3_path: Path
    audio: AudioCheck


def render_score(score: Score, directory: Path, name: str = "demo",
                 on_stage: Callable[[str], None] | None = None) -> RenderResult:
    stage = on_stage or (lambda _: None)
    directory.mkdir(parents=True, exist_ok=True)
    score_path = directory / f"{name}.score.json"
    score_path.write_text(score.model_dump_json(by_alias=True, indent=1), encoding="utf-8")
    stage("rendering")
    midi_path = write_midi(score, directory / f"{name}.mid", tail_seconds=load_composition().tail_seconds)
    wav = render_wav(midi_path, directory / f"{name}.wav")
    stage("encoding")
    mp3_path = encode_mp3(wav.path, directory / f"{name}.mp3")
    stage("checking")
    return RenderResult(score_path, midi_path, wav, mp3_path, check_final_audio(mp3_path))
