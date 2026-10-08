"""worker 失败与重启检查（使用临时运行目录，不影响 runtime/）：

1. 模拟渲染失败（FluidSynth 路径无效）→ 任务 failed，带明确错误；
2. worker 处理中被强制结束 → 重启后遗留的运行中任务变为 failed；
3. 每个任务独立目录，新任务（成功或失败）不覆盖上一次成功的音频。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from app import worker
from app.providers.mock import MockProvider
from app.schemas.job import MusicJobCreate
from app.settings import settings
from app.storage.jobs import JobStore

LYRICS = "[主歌]\n晚风吹过街角\n你笑着回头\n路灯一盏一盏\n照亮我们的路\n[副歌]\n就这样走下去\n不怕夜太长\n就这样走下去\n心里有光"


def _request(n: int) -> MusicJobCreate:
    return MusicJobCreate.model_validate({
        "requestId": f"check_worker_{n:04d}", "lyrics": LYRICS,
        "input": {"themeId": "love", "emotionId": "warm", "styleId": "pop"},
    })


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _mark(ok: bool) -> str:
    return "✅" if ok else "❌"


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="ai-music-worker-check-"))
    worker.runtime_dir = lambda: root
    store = JobStore(root / "app.db")
    env = {**os.environ, "RUNTIME_DIR": str(root), "MODEL_PROVIDER": "mock"}
    backend = Path(__file__).resolve().parents[1]
    results = []
    print(f"临时运行目录：{root}（检查结束后删除）\n")

    a, _ = store.create(_request(1))
    a = worker.run_once(store, MockProvider())
    a_mp3 = root / a.audio_path
    a_hash = _digest(a_mp3)
    print(f"{_mark(a.status == 'succeeded')} 任务 A 成功：{a.audio_path}（{a.duration_seconds} 秒，指纹 {a_hash}）")
    results.append(a.status == "succeeded")

    original = settings.fluidsynth_path
    settings.fluidsynth_path = "/nonexistent/fluidsynth"
    try:
        store.create(_request(2))
        b = worker.run_once(store, MockProvider())
    finally:
        settings.fluidsynth_path = original
    ok = b.status == "failed" and b.error_code == "FLUIDSYNTH_UNAVAILABLE" and b.audio_path is None
    print(f"{_mark(ok)} 任务 B 模拟渲染失败：状态 {b.status}，错误 [{b.error_code}] {b.error_message}")
    results.append(ok)

    c, _ = store.create(_request(3))
    process = subprocess.Popen([sys.executable, "-m", "app.worker"], cwd=backend, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 30
    while store.get(c.id).status == "queued" and time.monotonic() < deadline:
        time.sleep(0.02)
    stage = store.get(c.id).stage
    process.send_signal(signal.SIGKILL)
    process.wait()
    killed = store.get(c.id)
    print(f"{_mark(killed.status == 'running')} 任务 C 处理中（阶段 {stage}）强制结束 worker：状态仍为 {killed.status}")
    subprocess.run([sys.executable, "-m", "app.worker", "--once"], cwd=backend, env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    c = store.get(c.id)
    ok = killed.status == "running" and c.status == "failed" and c.error_code == "WORKER_INTERRUPTED"
    print(f"{_mark(ok)} 重启 worker 后任务 C：状态 {c.status}，错误 [{c.error_code}] {c.error_message}")
    results.append(ok)

    store.create(_request(4))
    d = worker.run_once(store, MockProvider())
    ok = d.status == "succeeded" and d.audio_path != a.audio_path and _digest(a_mp3) == a_hash
    print(f"{_mark(ok)} 任务 D 成功：{d.audio_path}；任务 A 的音频仍在且未变（指纹 {_digest(a_mp3)}）")
    results.append(ok)

    dirs = sorted(p.name for p in (root / "jobs").iterdir())
    print(f"\n各任务目录：{dirs}")
    for name in dirs:
        print(f"  {name}/：{sorted(p.name for p in (root / 'jobs' / name).iterdir()) or '（空）'}")
    shutil.rmtree(root, ignore_errors=True)
    print("\n全部检查符合预期。" if all(results) else "\n存在不符合预期的检查。")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
