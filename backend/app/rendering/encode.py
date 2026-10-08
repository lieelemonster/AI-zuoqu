"""WAV 编码为 MP3，并检查成品能否解码及时长是否在允许范围内。"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.presets import load_composition
from app.rendering.audio import RenderError, inspect_wav
from app.rendering.environment import check_ffmpeg

FFMPEG_TIMEOUT_SECONDS = 120
MAX_GAIN_DB = 20.0


@dataclass(frozen=True)
class AudioCheck:
    path: Path
    ok: bool
    duration_seconds: float | None
    size_bytes: int
    codec: str | None
    errors: list[str] = field(default_factory=list)


def _ffmpeg() -> str:
    result = check_ffmpeg()
    if not result.ok:
        raise RenderError("FFMPEG_UNAVAILABLE", f"FFmpeg 不可用：{result.detail}")
    return result.path


def _run(command: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RenderError("FFMPEG_TIMEOUT", f"FFmpeg 处理超过 {FFMPEG_TIMEOUT_SECONDS} 秒") from exc


def encode_mp3(wav_path: Path, mp3_path: Path) -> Path:
    """按峰值把响度调到目标值后编码 MP3；先写临时文件，成功后再改名。"""
    config = load_composition()
    ffmpeg = _ffmpeg()
    info = inspect_wav(wav_path)
    if info.peak <= 0:
        raise RenderError("RENDER_SILENT", "WAV 没有声音，无法编码")
    gain_db = min(config.target_peak_dbfs - info.peak_dbfs, MAX_GAIN_DB)

    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = mp3_path.with_name(f".{mp3_path.stem}.{os.getpid()}.tmp.mp3")
    completed = _run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(wav_path),
        "-af", f"volume={gain_db:.2f}dB",
        "-codec:a", "libmp3lame", "-b:a", config.mp3_bitrate, "-ar", "44100", "-ac", "2",
        "-f", "mp3", str(temp_path),
    ])
    if completed.returncode != 0 or not temp_path.is_file() or temp_path.stat().st_size == 0:
        temp_path.unlink(missing_ok=True)
        raise RenderError("ENCODE_FAILED", f"MP3 编码失败：{completed.stderr.strip()[-300:]}")
    temp_path.replace(mp3_path)
    return mp3_path


def probe_audio(path: Path) -> tuple[float | None, str | None, str]:
    """返回（时长秒数，编码格式，错误信息）。优先使用与 FFmpeg 同目录的 ffprobe。"""
    ffmpeg = _ffmpeg()
    ffprobe = Path(ffmpeg).with_name("ffprobe")
    if ffprobe.is_file():
        completed = _run([
            str(ffprobe), "-v", "error", "-show_entries", "format=duration:stream=codec_name",
            "-of", "json", str(path),
        ])
        if completed.returncode != 0:
            return None, None, completed.stderr.strip()[-300:] or "无法读取音频信息"
        data = json.loads(completed.stdout or "{}")
        duration = data.get("format", {}).get("duration")
        codec = next((s.get("codec_name") for s in data.get("streams", [])), None)
        return (float(duration) if duration else None), codec, ""
    completed = _run([ffmpeg, "-hide_banner", "-i", str(path)])
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", completed.stderr)
    codec = re.search(r"Audio: (\w+)", completed.stderr)
    if not match:
        return None, None, "无法读取音频时长"
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s), codec.group(1) if codec else None, ""


def check_final_audio(path: Path) -> AudioCheck:
    """成品检查：文件非空、完整解码无错误、MP3 编码、时长在配置范围内。"""
    config = load_composition()
    if not path.is_file() or path.stat().st_size == 0:
        return AudioCheck(path, False, None, 0, None, ["音频文件不存在或为空"])
    size = path.stat().st_size
    errors = []
    duration, codec, probe_error = probe_audio(path)
    if probe_error:
        errors.append(probe_error)
    decoded = _run([_ffmpeg(), "-v", "error", "-i", str(path), "-f", "null", "-"])
    if decoded.returncode != 0 or decoded.stderr.strip():
        errors.append(f"解码出错：{decoded.stderr.strip()[-200:]}")
    if codec != "mp3":
        errors.append(f"编码格式应为 mp3，实际为 {codec}")
    if duration is None:
        errors.append("无法得到时长")
    elif not config.min_seconds <= duration <= config.max_seconds:
        errors.append(f"时长 {duration:.1f} 秒，超出允许范围 {config.min_seconds:g}～{config.max_seconds:g} 秒")
    return AudioCheck(path, not errors, duration, size, codec, errors)
