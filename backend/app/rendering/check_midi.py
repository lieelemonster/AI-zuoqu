"""MIDI 导出检查：中央 C、起点 0、480 tick、120 BPM 读回应为一拍、约 0.5 秒。"""

from pathlib import Path

from app.rendering.midi import read_midi_notes, write_midi
from app.schemas.score import Score
from app.settings import PROJECT_ROOT

CHECK_DIR = PROJECT_ROOT / "runtime" / "checks"


def middle_c_score() -> Score:
    return Score.model_validate({
        "bpm": 120,
        "sections": [{"id": "verse_1", "type": "verse", "startTick": 0, "durationTicks": 1920}],
        "tracks": [
            {"role": "melody", "program": 0, "notes": [
                {"pitch": 60, "startTick": 0, "durationTicks": 480, "velocity": 90},
            ]},
            {"role": "accompaniment", "program": 0, "notes": [
                {"pitch": p, "startTick": 0, "durationTicks": 1920, "velocity": 60} for p in (48, 52, 55)
            ]},
        ],
    })


def main() -> int:
    path = write_midi(middle_c_score(), CHECK_DIR / "middle_c.mid")
    midi, notes = read_midi_notes(Path(path))
    print(f"已写入 {path}")
    print(f"MIDI type {midi.type}，每拍 {midi.ticks_per_beat} tick，共 {len(midi.tracks)} 条轨道：")
    for track in midi.tracks:
        name = next((m.name for m in track if m.type == "track_name"), "?")
        count = sum(1 for m in track if m.type == "note_on")
        print(f"  - {name}：{count} 个音符")

    melody = [n for n in notes if n.track_name == "melody"]
    accompaniment = [n for n in notes if n.track_name == "accompaniment"]
    note = melody[0]
    beats = note.duration_ticks / midi.ticks_per_beat
    print(
        f"旋律读回：音高 {note.pitch}（中央 C），起点 tick {note.start_tick}，"
        f"时长 {note.duration_ticks} tick = {beats:g} 拍 = {note.duration_seconds:.3f} 秒，通道 {note.channel}"
    )
    print(f"伴奏读回：{len(accompaniment)} 个音符，通道 {accompaniment[0].channel}")

    ok = (
        note.pitch == 60 and note.start_tick == 0 and beats == 1
        and abs(note.duration_seconds - 0.5) < 1e-6
        and len(accompaniment) == 3 and note.channel != accompaniment[0].channel
    )
    print("\n检查通过：一拍约 0.5 秒，旋律与伴奏为独立轨道。" if ok else "\n检查失败。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
