import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.job import MusicJobCreate
from app.storage.jobs import JobStore, get_store

LYRICS = "[主歌]\n晚风吹过街角\n你笑着回头\n[副歌]\n就这样走下去\n心里有光"
AUDIO = bytes(range(256)) * 400


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "app.db")


@pytest.fixture
def client(store):
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_job(store, tmp_path, request_id="req_audio_0001", audio_path="auto", write=True):
    job, _ = store.create(MusicJobCreate.model_validate({
        "requestId": request_id, "lyrics": LYRICS, "input": {"themeId": "love", "emotionId": "sweet",
                                                             "styleId": "pop"}}))
    store.claim_next()
    path = f"jobs/{job.id}/song.mp3" if audio_path == "auto" else audio_path
    if write:
        (tmp_path / "jobs" / job.id).mkdir(parents=True)
        (tmp_path / "jobs" / job.id / "song.mp3").write_bytes(AUDIO)
    store.succeed(job.id, score_path="s", midi_path="m", audio_path=path, duration_seconds=55.0)
    return job


def test_succeeded_view_has_urls(client, store, tmp_path):
    job = make_job(store, tmp_path)
    view = client.get(f"/api/music-jobs/{job.id}").json()
    assert view["status"] == "succeeded" and view["durationSeconds"] == 55.0
    assert view["audioUrl"] == f"/api/music-jobs/{job.id}/audio"
    assert view["downloadUrl"] == f"/api/music-jobs/{job.id}/download"


def test_audio_full_and_range(client, store, tmp_path):
    job = make_job(store, tmp_path)
    full = client.get(f"/api/music-jobs/{job.id}/audio")
    assert full.status_code == 200 and full.content == AUDIO
    assert full.headers["content-type"] == "audio/mpeg" and full.headers["accept-ranges"] == "bytes"
    assert "attachment" not in full.headers.get("content-disposition", "")

    part = client.get(f"/api/music-jobs/{job.id}/audio", headers={"Range": "bytes=1000-1999"})
    assert part.status_code == 206 and part.content == AUDIO[1000:2000]
    assert part.headers["content-range"] == f"bytes 1000-1999/{len(AUDIO)}"

    tail = client.get(f"/api/music-jobs/{job.id}/audio", headers={"Range": "bytes=-100"})
    assert tail.status_code == 206 and tail.content == AUDIO[-100:]

    bad = client.get(f"/api/music-jobs/{job.id}/audio", headers={"Range": f"bytes={len(AUDIO) + 10}-"})
    assert bad.status_code == 416


def test_download_is_same_file_with_attachment_header(client, store, tmp_path):
    job = make_job(store, tmp_path)
    download = client.get(f"/api/music-jobs/{job.id}/download")
    assert download.status_code == 200 and download.content == AUDIO
    disposition = download.headers["content-disposition"]
    assert disposition.startswith("attachment") and ".mp3" in disposition


def test_not_ready_job(client, store):
    job, _ = store.create(MusicJobCreate.model_validate({
        "requestId": "req_audio_wait", "lyrics": LYRICS,
        "input": {"themeId": "love", "emotionId": "sweet", "styleId": "pop"}}))
    for suffix in ("audio", "download"):
        response = client.get(f"/api/music-jobs/{job.id}/{suffix}")
        assert response.status_code == 409 and response.json()["error"]["code"] == "AUDIO_NOT_READY"


def test_missing_or_cleaned_audio(client, store, tmp_path):
    missing = make_job(store, tmp_path, "req_audio_0002", write=False)
    assert client.get(f"/api/music-jobs/{missing.id}/audio").status_code == 410
    cleaned = make_job(store, tmp_path, "req_audio_0003")
    store.clear_files(cleaned.id)
    assert client.get(f"/api/music-jobs/{cleaned.id}").json()["audioUrl"] is None
    assert client.get(f"/api/music-jobs/{cleaned.id}/download").json()["error"]["code"] == "AUDIO_REMOVED"


def test_path_outside_runtime_is_refused(client, store, tmp_path):
    outside = tmp_path.parent / "secret.mp3"
    outside.write_bytes(b"secret")
    job = make_job(store, tmp_path, "req_audio_0004", audio_path="../secret.mp3", write=False)
    assert client.get(f"/api/music-jobs/{job.id}/audio").status_code == 410


def test_unknown_job(client):
    assert client.get("/api/music-jobs/job_nope/download").status_code == 404
