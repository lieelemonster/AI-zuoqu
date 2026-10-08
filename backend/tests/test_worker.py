import pytest

from app import worker
from app.providers.mock import MockProvider
from app.rendering.environment import check_audio_environment
from app.schemas.job import MusicJobCreate
from app.storage.jobs import JobStore

LYRICS = "[主歌]\n晚风吹过街角\n你笑着回头\n路灯一盏一盏\n照亮我们的路\n[副歌]\n就这样走下去\n不怕夜太长\n就这样走下去\n心里有光"
needs_audio = pytest.mark.skipif(not all(r.ok for r in check_audio_environment()), reason="音频工具未安装")


def request(request_id: str, style="pop") -> MusicJobCreate:
    return MusicJobCreate.model_validate({
        "requestId": request_id, "lyrics": LYRICS,
        "input": {"themeId": "love", "emotionId": "sweet", "styleId": style},
    })


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "runtime_dir", lambda: tmp_path)
    return JobStore(tmp_path / "app.db")


def test_claim_is_fifo_and_exclusive(store):
    first, _ = store.create(request("req_claim_0001"))
    second, _ = store.create(request("req_claim_0002"))
    claimed = store.claim_next()
    assert claimed.id == first.id and claimed.status == "running" and claimed.started_at
    assert store.claim_next().id == second.id
    assert store.claim_next() is None


def test_empty_queue_returns_none(store):
    assert worker.run_once(store, MockProvider()) is None


@needs_audio
def test_worker_runs_plan_compose_render(store, tmp_path):
    job, _ = store.create(request("req_worker_0001"))
    stages = []
    original = store.set_stage
    store.set_stage = lambda job_id, stage: (stages.append(stage), original(job_id, stage))
    done = worker.run_once(store, MockProvider())
    assert done.id == job.id and done.status == "succeeded" and done.stage == "done"
    assert stages == ["composing", "rendering", "encoding", "checking"]
    assert 45 <= done.duration_seconds <= 75
    assert done.plan_source == "ai" and done.model_id == "mock" and done.composer_version
    assert done.audio_path == f"jobs/{job.id}/song.mp3" and (tmp_path / done.audio_path).stat().st_size > 100_000
    assert store.plan_record(job.id)["source"] == "ai"


@needs_audio
def test_worker_without_model_uses_default_plan(store, monkeypatch):
    store.create(request("req_worker_0002", style="folk"))
    monkeypatch.setattr(worker, "_provider", lambda: None)
    done = worker.run_once(store)
    assert done.status == "succeeded" and done.plan_source == "default"
    assert store.plan_record(done.id)["fallbackReason"]
