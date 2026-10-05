"""Keyless trip checks must return an honest route without live traffic claims."""
from unittest.mock import patch
import requests

from src.integrations.traffic import serpapi_service as traffic


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_da_lat_resolves_without_serpapi():
    with patch.object(traffic, "_keys", return_value=[]):
        lat, lon, name = traffic.search_location_google("Đà Lạt")
    assert 11.9 < lat < 12.0
    assert 108.4 < lon < 108.5
    assert "Lâm Đồng" in name


def test_public_geocode_ignores_unrelated_same_country_result():
    response = FakeResponse({"results": [
        {"name": "Hà Nội", "country_code": "VN", "latitude": 20.47,
         "longitude": 106.02, "admin1": "Ninh Binh", "population": None},
        {"name": "Hanoi", "country_code": "VN", "latitude": 21.02,
         "longitude": 105.84, "admin1": "Hanoi", "population": 8000000},
    ]})
    with patch.object(traffic.requests, "get", return_value=response) as get:
        lat, lon, _ = traffic._public_geocode("Hà Nội")
    assert (lat, lon) == (21.02, 105.84)
    assert get.call_args.kwargs["params"]["name"] == "Hanoi"


def test_osrm_route_does_not_invent_live_traffic():
    response = FakeResponse({"code": "Ok", "routes": [{
        "distance": 290256.4, "duration": 13394.4, "geometry": "encoded-route",
    }]})
    with patch.object(traffic, "_keys", return_value=[]), \
         patch.object(traffic, "TRACKASIA_KEY", ""), \
         patch.object(traffic.requests, "get", return_value=response):
        result = traffic.check_route_traffic_google(
            "Ho Chi Minh", "Da Lat", 10.81, 106.70, 11.94, 108.44,
        )
    assert result["distance_km"] == 290.3
    assert result["time_normal_min"] == 223
    assert result["traffic_available"] is False
    assert result["status"] == "unknown"
    assert result["time_traffic_min"] is None
    assert result["speed_kmh"] is None
    assert result["route_polyline_type"] == "polyline6"


def test_osrm_timeout_returns_missing_route_without_exposing_exception():
    with patch.object(traffic, "TRACKASIA_KEY", ""), \
         patch.object(traffic.requests, "get", side_effect=requests.ConnectTimeout("private network detail")):
        result = traffic._route_without_live_traffic(10.81, 106.70, 11.94, 108.44)
    assert result["route_available"] is False
    assert result["traffic_available"] is False
    assert result["distance_km"] is None
    assert result["time_normal_min"] is None
    assert result["route_polyline"] is None
    assert "private network detail" not in str(result)


def test_trackasia_route_is_used_before_unavailable_osrm():
    response = FakeResponse({"code": "Ok", "routes": [{
        "distance": 294997.2, "duration": 18494.8, "geometry": "trackasia-encoded-route",
    }]})
    with patch.object(traffic, "TRACKASIA_KEY", "test-key"), \
         patch.object(traffic.requests, "get", return_value=response) as get:
        result = traffic._route_without_live_traffic(10.5417, 107.242, 11.94646, 108.44193)
    assert result["route_available"] is True
    assert result["traffic_available"] is False
    assert result["traffic_source"] == "trackasia"
    assert result["distance_km"] == 295.0
    assert result["time_normal_min"] == 308
    assert result["route_polyline_type"] == "polyline"
    assert get.call_count == 1


def test_trackasia_timeout_uses_osrm_route():
    response = FakeResponse({"code": "Ok", "routes": [{
        "distance": 300000, "duration": 18000, "geometry": "osrm-encoded-route",
    }]})
    with patch.object(traffic, "TRACKASIA_KEY", "test-key"), \
         patch.object(traffic.requests, "get", side_effect=[requests.ConnectTimeout(), response]) as get:
        result = traffic._route_without_live_traffic(10.5417, 107.242, 11.94646, 108.44193)
    assert result["route_available"] is True
    assert result["traffic_source"] == "osrm"
    assert result["route_polyline_type"] == "polyline6"
    assert get.call_count == 2
