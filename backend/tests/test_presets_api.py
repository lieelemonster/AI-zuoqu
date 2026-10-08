from fastapi.testclient import TestClient

from app.main import app


def test_presets_endpoint_lists_all_options():
    data = TestClient(app).get("/api/presets").json()
    assert len(data["themes"]) == 10 and len(data["emotions"]) == 10 and len(data["styles"]) == 7
    assert {"id": "folk", "name": "民谣"} in data["styles"]
    assert data["themes"][0].keys() == {"id", "name"}
