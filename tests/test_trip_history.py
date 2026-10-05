from unittest.mock import patch

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


def _run_trip(client, headers=None, destination="Đà Lạt"):
    with patch("src.api.app.search_location_google", return_value=(11.9404, 108.4583, f"{destination}, Lâm Đồng, Việt Nam")), \
         patch("src.api.app.check_route_traffic_google", return_value=dict(FAKE_TRAFFIC)), \
         patch("src.api.app.ensure_route_polyline", return_value=None):
        return client.get(
            "/trip",
            params={"destination": destination, "lat": "10.77", "lon": "106.69"},
            headers=headers or {},
        )


def test_trip_history_empty_for_new_user(client, auth_headers):
    resp = client.get("/api/trip-history", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["results"] == []


def test_authenticated_trip_is_saved_to_history(client, auth_headers):
    trip_resp = _run_trip(client, headers=auth_headers, destination="Nha Trang")
    assert trip_resp.status_code == 200

    hist_resp = client.get("/api/trip-history", headers=auth_headers)
    assert hist_resp.status_code == 200
    results = hist_resp.json()["results"]
    assert len(results) == 1
    assert results[0]["destination"] == "Nha Trang"


def test_cached_trip_is_also_saved_to_history(client, auth_headers):
    first = _run_trip(client, headers=auth_headers, destination="Đà Lạt cache history test")
    second = _run_trip(client, headers=auth_headers, destination="Đà Lạt cache history test")
    assert first.status_code == second.status_code == 200
    assert second.json()["_cached"] is True
    rows = client.get("/api/trip-history", headers=auth_headers).json()["results"]
    assert len([row for row in rows if row["destination"] == "Đà Lạt cache history test"]) == 2


def test_anonymous_trip_not_saved(client, auth_headers):
    # Anonymous request (no Authorization header) should not create history
    # for this user even though we check with their token afterwards.
    resp = client.get("/api/trip-history", headers=auth_headers)
    before = len(resp.json()["results"])

    anon_resp = _run_trip(client, headers=None, destination="Hội An")
    assert anon_resp.status_code == 200

    resp2 = client.get("/api/trip-history", headers=auth_headers)
    after = len(resp2.json()["results"])
    assert after == before


def test_trip_history_requires_auth(client):
    resp = client.get("/api/trip-history")
    assert resp.status_code == 401


def test_delete_trip_history(client, auth_headers):
    _run_trip(client, headers=auth_headers, destination="Phú Quốc")
    results = client.get("/api/trip-history", headers=auth_headers).json()["results"]
    trip_id = results[0]["id"]

    del_resp = client.delete(f"/api/trip-history/{trip_id}", headers=auth_headers)
    assert del_resp.status_code == 200

    del_again = client.delete(f"/api/trip-history/{trip_id}", headers=auth_headers)
    assert del_again.status_code == 404
