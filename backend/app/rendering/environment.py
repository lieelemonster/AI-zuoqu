"""检查音频渲染所需的 FluidSynth、FFmpeg 和钢琴 SF2 音源。"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.settings import PROJECT_ROOT, settings

# macOS 首次运行新装的程序会扫描其动态库，可能超过 10 秒。
VERSION_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class CheckResult:
    name: str
    env_var: str
    ok: bool
    path: str
    detail: str


def resolve_path(value: str) -> Path | None:
    """空值视为未配置；相对路径以项目根目录为基准。"""
    value = value.strip()
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def _check_program(name: str, env_var: str, value: str, version_args: list[str]) -> CheckResult:
    path = resolve_path(value)
    if path is None:
        return CheckResult(name, env_var, False, "", f"未配置 {env_var}，请在 .env 中填写可执行文件路径")
    if not path.is_file():
        return CheckResult(name, env_var, False, str(path), f"{env_var} 指向的文件不存在")
    if not os.access(path, os.X_OK):
        return CheckResult(name, env_var, False, str(path), f"{env_var} 指向的文件不可执行")
    try:
        completed = subprocess.run(
            [str(path), *version_args],
            capture_output=True,
            text=True,
            timeout=VERSION_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckResult(name, env_var, False, str(path), f"无法运行：{exc}")
    output = (completed.stdout or completed.stderr).strip().splitlines()
    if completed.returncode != 0 or not output:
        return CheckResult(name, env_var, False, str(path), f"运行版本命令失败，退出码 {completed.returncode}")
    return CheckResult(name, env_var, True, str(path), output[0])


def check_soundfont(value: str | None = None) -> CheckResult:
    env_var = "SOUNDFONT_PATH"
    path = resolve_path(settings.soundfont_path if value is None else value)
    if path is None:
        return CheckResult("钢琴音源", env_var, False, "", f"未配置 {env_var}，请在 .env 中填写 .sf2 音源路径")
    if not path.is_file():
        return CheckResult("钢琴音源", env_var, False, str(path), f"{env_var} 指向的音源文件不存在")
    with path.open("rb") as file:
        header = file.read(12)
    if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"sfbk":
        return CheckResult("钢琴音源", env_var, False, str(path), "文件不是有效的 SF2 音源（缺少 RIFF/sfbk 头）")
    size_mb = path.stat().st_size / 1024 / 1024
    return CheckResult("钢琴音源", env_var, True, str(path), f"SF2 音源，{size_mb:.1f} MB")


def check_fluidsynth(value: str | None = None) -> CheckResult:
    return _check_program(
        "FluidSynth", "FLUIDSYNTH_PATH",
        settings.fluidsynth_path if value is None else value, ["--version"],
    )


def check_ffmpeg(value: str | None = None) -> CheckResult:
    return _check_program(
        "FFmpeg", "FFMPEG_PATH",
        settings.ffmpeg_path if value is None else value, ["-version"],
    )


def verify_soundfont_loads(fluidsynth: CheckResult, soundfont: CheckResult) -> CheckResult:
    """让 FluidSynth 实际加载一次音源；不传 MIDI 时成功加载会提示未指定 MIDI 文件。"""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            completed = subprocess.run(
                [fluidsynth.path, "-ni", "-q", "-F", str(Path(tmp) / "probe.wav"), soundfont.path],
                capture_output=True,
                text=True,
                timeout=VERSION_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CheckResult(soundfont.name, soundfont.env_var, False, soundfont.path, f"FluidSynth 加载音源失败：{exc}")
    output = f"{completed.stdout}\n{completed.stderr}"
    if "Failed to load" in output or "not a SoundFont" in output:
        return CheckResult(soundfont.name, soundfont.env_var, False, soundfont.path, "FluidSynth 无法加载该音源文件")
    return CheckResult(soundfont.name, soundfont.env_var, True, soundfont.path, f"{soundfont.detail}，FluidSynth 加载成功")


def check_audio_environment() -> list[CheckResult]:
    fluidsynth, ffmpeg, soundfont = check_fluidsynth(), check_ffmpeg(), check_soundfont()
    if fluidsynth.ok and soundfont.ok:
        soundfont = verify_soundfont_loads(fluidsynth, soundfont)
    return [fluidsynth, ffmpeg, soundfont]


def main() -> int:
    results = check_audio_environment()
    for result in results:
        mark = "✅" if result.ok else "❌"
        print(f"{mark} {result.name}（{result.env_var}）：{result.detail}")
        if result.path:
            print(f"   路径：{result.path}")
    missing = [result for result in results if not result.ok]
    if missing:
        print(f"\n音频环境不完整，缺失或不可用：{'、'.join(r.name for r in missing)}")
        return 1
    print("\n音频环境可用：FluidSynth、FFmpeg 和钢琴音源均已就绪。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
