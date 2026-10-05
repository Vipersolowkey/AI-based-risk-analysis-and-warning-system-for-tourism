"""Covers /trip end-to-end via TestClient. External services (SerpAPI geocode +
directions) are mocked so CI doesn't depend on live keys/network."""
from unittest.mock import patch
import pytest


FAKE_TRAFFIC = {
    "distance_km": 310.0,
    "time_normal_min": 300,
    "time_traffic_min": 320,
    "delay_min": 20,
    "ratio": 1.07,
    "speed_kmh": 60.0,
    "status": "light",
    "status_emoji": "🟢",
    "traffic_score": 2,
    "route_polyline": None,
}


def test_trip_success_anonymous(client):
    with patch("src.api.app.search_location_google", return_value=(11.9404, 108.4583, "Đà Lạt, Lâm Đồng, Việt Nam")), \
         patch("src.api.app.check_route_traffic_google", return_value=dict(FAKE_TRAFFIC)), \
         patch("src.api.app.ensure_route_polyline", return_value=None):
        resp = client.get(
            "/trip",
            params={"destination": "Đà Lạt", "lat": "10.77", "lon": "106.69", "trip_purpose": "dating"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["to"]["name"] == "Đà Lạt, Lâm Đồng, Việt Nam"
    assert data["matched_province"] == "Lâm Đồng"
    assert "recommendation" in data


def test_trip_destination_not_found(client):
    with patch("src.api.app.search_location_google", return_value=(None, None, None)):
        resp = client.get(
            "/trip",
            params={"destination": "Xyz Nowhere", "lat": "10.77", "lon": "106.69"},
        )
    assert resp.status_code == 404


def test_trip_invalid_coords(client):
    resp = client.get(
        "/trip",
        params={"destination": "Đà Lạt", "lat": "not-a-number", "lon": "106.69"},
    )
    assert resp.status_code == 422


def test_trip_without_live_traffic_reports_estimate_as_uncertain(client):
    from src.api import app as api_module

    route = {
        "distance_km": 294.0, "time_normal_min": 227, "time_traffic_min": None,
        "speed_kmh": None, "status": "unknown", "traffic_score": None,
        "traffic_available": False, "traffic_source": "osrm",
        "route_polyline": "encoded-route", "route_polyline_type": "polyline6",
    }
    api_module._trip_cache.clear()
    with patch("src.api.app.search_location_google", return_value=(11.94646, 108.44193, "Đà Lạt, Lâm Đồng, Việt Nam")), \
         patch("src.api.app.check_route_traffic_google", return_value=route), \
         patch("src.api.app.ensure_route_polyline", return_value=None), \
         patch("src.api.app.weather_model_system", None):
        response = client.get("/trip", params={
            "destination": "Đà Lạt", "lat": "10.8119", "lon": "106.7066", "trip_purpose": "dating",
        })
    assert response.status_code == 200
    result = response.json()
    assert result["traffic"]["traffic_available"] is False
    assert result["traffic"]["time_traffic_min"] is None
    assert "chưa có dữ liệu giao thông trực tiếp" in result["recommendation"]


@pytest.mark.parametrize("lat,lon", [
    ("nan", "106.69"), ("10.77", "inf"), ("91", "106.69"), ("10.77", "-181"),
])
def test_trip_rejects_nonfinite_or_out_of_range_coords(client, lat, lon):
    response = client.get("/trip", params={"destination": "Da Lat", "lat": lat, "lon": lon})
    assert response.status_code == 422


def test_trip_traffic_provider_error_keeps_partial_trip_result(client):
    from src.api import app as api_module
    api_module._trip_cache.clear()
    with patch("src.api.app.search_location_google", return_value=(11.94, 108.44, "Đà Lạt, Lâm Đồng, Việt Nam")), \
         patch("src.api.app.check_route_traffic_google", side_effect=RuntimeError("private detail")), \
         patch("src.api.app.ensure_route_polyline") as ensure_polyline, \
         patch("src.api.app.weather_model_system", None):
        resp = client.get("/trip", params={
            "destination": "Đà Lạt internal error test", "lat": "10.77", "lon": "106.69",
        })
    assert resp.status_code == 200
    result = resp.json()
    assert result["traffic"]["route_available"] is False
    assert result["traffic"]["distance_km"] is None
    assert result["traffic"]["time_normal_min"] is None
    assert "risk" in result and "weather" in result
    assert "chưa lấy được tuyến đường" in result["recommendation"]
    ensure_polyline.assert_not_called()
    assert not api_module._trip_cache
    assert "private detail" not in resp.text
    assert "traceback" not in resp.text


def test_traffic_route_provider_error_returns_explicit_missing_data(client):
    with patch("src.api.app.search_location_google", return_value=(11.94, 108.44, "Đà Lạt")), \
         patch("src.api.app.check_route_traffic_google", side_effect=RuntimeError("private detail")), \
         patch("src.api.app.ensure_route_polyline") as ensure_polyline:
        resp = client.get("/traffic/route", params={"from_addr": "A", "to_addr": "B"})
    assert resp.status_code == 200
    assert resp.json()["traffic"]["route_available"] is False
    assert resp.json()["traffic"]["time_normal_min"] is None
    ensure_polyline.assert_not_called()
    assert "private detail" not in resp.text
