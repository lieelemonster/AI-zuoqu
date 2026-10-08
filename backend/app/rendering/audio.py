"""调用 FluidSynth 把 MIDI 渲染为 WAV，并检查峰值。进程以参数数组启动，不经过 shell。"""

from __future__ import annotations

import array
import math
import os
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

from app.rendering.environment import check_fluidsynth, check_soundfont

SAMPLE_RATE = 44100
# FluidSynth 增益；渲染结果留出余量，最终响度在 MP3 编码时统一调整。
SYNTH_GAIN = 1.0
RENDER_TIMEOUT_SECONDS = 180
CLIP_THRESHOLD = 0.999
SILENCE_LEVEL = 33  # 约 -60 dBFS
TRIM_PADDING_SECONDS = 0.25


class RenderError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class WavInfo:
    path: Path
    size_bytes: int
    duration_seconds: float
    channels: int
    sample_rate: int
    peak: float
    clipped_samples: int

    @property
    def peak_dbfs(self) -> float:
        return 20 * math.log10(self.peak) if self.peak > 0 else float("-inf")


def inspect_wav(path: Path) -> WavInfo:
    with wave.open(str(path), "rb") as wav:
        channels, width, rate, frames = wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()
        data = wav.readframes(frames)
    if width != 2:
        raise RenderError("WAV_FORMAT", f"仅支持 16 位 WAV，收到 {width * 8} 位")
    samples = array.array("h")
    samples.frombytes(data)
    if sys.byteorder == "big":
        samples.byteswap()
    peak_raw = max((abs(s) for s in samples), default=0)
    limit = int(32767 * CLIP_THRESHOLD)
    clipped = sum(1 for s in samples if abs(s) >= limit)
    return WavInfo(
        path=path,
        size_bytes=path.stat().st_size,
        duration_seconds=frames / rate if rate else 0.0,
        channels=channels,
        sample_rate=rate,
        peak=peak_raw / 32768,
        clipped_samples=clipped,
    )


def trim_trailing_silence(path: Path) -> None:
    """FluidSynth 会在 MIDI 结束后补数秒静音；保留钢琴衰减到底噪为止，再加短淡出。"""
    with wave.open(str(path), "rb") as wav:
        params = wav.getparams()
        samples = array.array("h")
        samples.frombytes(wav.readframes(params.nframes))
    channels, rate = params.nchannels, params.framerate
    last = len(samples) - 1
    while last >= 0 and abs(samples[last]) <= SILENCE_LEVEL:
        last -= 1
    keep_frames = min(params.nframes, (last // channels) + 1 + int(TRIM_PADDING_SECONDS * rate))
    samples = samples[: keep_frames * channels]
    fade_frames = min(keep_frames, int(TRIM_PADDING_SECONDS * rate))
    for frame in range(fade_frames):
        factor = (fade_frames - frame) / fade_frames
        base = (keep_frames - fade_frames + frame) * channels
        for c in range(channels):
            samples[base + c] = int(samples[base + c] * factor)
    with wave.open(str(path), "wb") as wav:
        wav.setparams(params)
        wav.writeframes(samples.tobytes())


def render_wav(
    midi_path: Path,
    wav_path: Path,
    *,
    fluidsynth_path: str | None = None,
    soundfont_path: str | None = None,
    gain: float = SYNTH_GAIN,
) -> WavInfo:
    """渲染成功返回 WAV 信息；缺少程序或音源、渲染失败、结果为空或削顶时抛出 RenderError。"""
    fluidsynth = check_fluidsynth(fluidsynth_path)
    if not fluidsynth.ok:
        raise RenderError("FLUIDSYNTH_UNAVAILABLE", f"FluidSynth 不可用：{fluidsynth.detail}")
    soundfont = check_soundfont(soundfont_path)
    if not soundfont.ok:
        raise RenderError("SOUNDFONT_UNAVAILABLE", f"钢琴音源不可用：{soundfont.detail}")
    if not midi_path.is_file():
        raise RenderError("MIDI_MISSING", f"MIDI 文件不存在：{midi_path}")

    wav_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = wav_path.with_name(f".{wav_path.stem}.{os.getpid()}.tmp.wav")
    command = [
        fluidsynth.path, "-ni", "-q",
        "-F", str(temp_path), "-T", "wav", "-O", "s16",
        "-r", str(SAMPLE_RATE), "-g", str(gain),
        soundfont.path, str(midi_path),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=RENDER_TIMEOUT_SECONDS, check=False
        )
    except subprocess.TimeoutExpired as exc:
        temp_path.unlink(missing_ok=True)
        raise RenderError("RENDER_TIMEOUT", f"FluidSynth 渲染超过 {RENDER_TIMEOUT_SECONDS} 秒") from exc
    output = f"{completed.stdout}\n{completed.stderr}"
    if completed.returncode != 0 or "Failed to load" in output or "not a SoundFont" in output:
        temp_path.unlink(missing_ok=True)
        raise RenderError("RENDER_FAILED", f"FluidSynth 渲染失败（退出码 {completed.returncode}）：{output.strip()[-300:]}")
    if not temp_path.is_file() or temp_path.stat().st_size <= 44:
        temp_path.unlink(missing_ok=True)
        raise RenderError("RENDER_EMPTY", "FluidSynth 没有生成有效的 WAV 文件")

    trim_trailing_silence(temp_path)
    info = inspect_wav(temp_path)
    if info.peak == 0:
        temp_path.unlink(missing_ok=True)
        raise RenderError("RENDER_SILENT", "渲染结果没有声音，请检查音源和 MIDI 内容")
    if info.clipped_samples > 0:
        temp_path.unlink(missing_ok=True)
        raise RenderError("RENDER_CLIPPED", f"渲染结果有 {info.clipped_samples} 个采样削顶，需降低音量")
    temp_path.replace(wav_path)
    return WavInfo(**{**info.__dict__, "path": wav_path})
