from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def test_init_endpoint_returns_profiles():
    response = client.get("/api/init")
    assert response.status_code == 200
    data = response.json()

    assert "abilities" in data and data["abilities"]
    assert any(entry["label"] == "Construction" for entry in data["abilities"])
    assert data["base_weekly_limit"] >= 100000
    assert len(data["items"]) > 0
    sample = data["items"][0]
    assert {"item_id", "name", "category"}.issubset(sample)


def test_optimise_endpoint_handles_bonus_items():
    payload = {
        "ability_levels": {"22": 40, "34": 40, "47": 40},
        "bonus_item_ids": [1170000350],
        "crafting_slots": 2,
    }
    response = client.post("/api/optimise", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"]
    assert data["weekly_limit"] >= data["weekly_bonus"]
    assert data["plant_plots"] >= 0
    assert data["fish_ponds"] >= 0

    for item in data.get("items", []):
        assert item["multiplier"] in (1.0, 1.2)
        assert item["per_unit_facility_minutes"] is not None
