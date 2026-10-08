"""乐谱 JSON 导出为 MIDI。乐谱使用绝对 tick，写入 MIDI 时转为相对 delta tick。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import mido

from app.schemas.score import Score

CHANNELS = {"melody": 0, "accompaniment": 1}
# 分轨音量：伴奏低于旋律，避免盖住主旋律或叠加爆音。
TRACK_VOLUME = {"melody": 110, "accompaniment": 80}
REVERB_SEND = 40


def score_to_midi(score: Score, tail_seconds: float = 0.0) -> mido.MidiFile:
    """生成 type 1 MIDI：0 号为速度轨，其后每个声部一条轨道。

    tail_seconds 延长速度轨的结束时间，让渲染器保留钢琴尾音而不是在最后一个音符处截断。
    """
    midi = mido.MidiFile(type=1, ticks_per_beat=score.ppq)
    tail_ticks = round(tail_seconds * score.bpm / 60 * score.ppq)

    conductor = mido.MidiTrack()
    conductor.append(mido.MetaMessage("track_name", name="conductor", time=0))
    conductor.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(score.bpm), time=0))
    conductor.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    conductor.append(mido.MetaMessage("end_of_track", time=score.total_ticks + tail_ticks))
    midi.tracks.append(conductor)

    for track in score.tracks:
        channel = CHANNELS[track.role]
        events: list[tuple[int, int, mido.Message]] = []
        for note in track.notes:
            events.append((note.start_tick, 1, mido.Message(
                "note_on", channel=channel, note=note.pitch, velocity=note.velocity)))
            events.append((note.end_tick, 0, mido.Message(
                "note_off", channel=channel, note=note.pitch, velocity=0)))
        # 同一 tick 先处理 note_off，避免同音高相邻音符被提前关掉。
        events.sort(key=lambda item: (item[0], item[1]))

        midi_track = mido.MidiTrack()
        midi_track.append(mido.MetaMessage("track_name", name=track.role, time=0))
        midi_track.append(mido.Message("program_change", channel=channel, program=track.program, time=0))
        midi_track.append(mido.Message("control_change", channel=channel, control=7, value=TRACK_VOLUME[track.role], time=0))
        midi_track.append(mido.Message("control_change", channel=channel, control=91, value=REVERB_SEND, time=0))
        previous = 0
        for tick, _, message in events:
            midi_track.append(message.copy(time=tick - previous))
            previous = tick
        midi_track.append(mido.MetaMessage("end_of_track", time=0))
        midi.tracks.append(midi_track)
    return midi


def write_midi(score: Score, path: Path, tail_seconds: float = 0.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    score_to_midi(score, tail_seconds).save(path)
    return path


@dataclass(frozen=True)
class ReadNote:
    track_name: str
    channel: int
    pitch: int
    start_tick: int
    duration_ticks: int
    start_seconds: float
    duration_seconds: float


def read_midi_notes(path: Path) -> tuple[mido.MidiFile, list[ReadNote]]:
    """读回 MIDI，按轨道还原每个音符的绝对 tick 与秒数（仅支持单一速度）。"""
    midi = mido.MidiFile(path)
    tempo = next(
        (msg.tempo for track in midi.tracks for msg in track if msg.type == "set_tempo"),
        mido.bpm2tempo(120),
    )
    to_seconds = lambda ticks: mido.tick2second(ticks, midi.ticks_per_beat, tempo)  # noqa: E731
    notes: list[ReadNote] = []
    for track in midi.tracks:
        name = next((msg.name for msg in track if msg.type == "track_name"), "")
        now = 0
        active: dict[tuple[int, int], int] = {}
        for msg in track:
            now += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                active[(msg.channel, msg.note)] = now
            elif msg.type in ("note_off", "note_on"):
                start = active.pop((msg.channel, msg.note), None)
                if start is not None:
                    notes.append(ReadNote(
                        name, msg.channel, msg.note, start, now - start,
                        to_seconds(start), to_seconds(now - start),
                    ))
    return midi, notes
