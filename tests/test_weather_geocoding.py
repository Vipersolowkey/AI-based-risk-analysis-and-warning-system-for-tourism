from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.api import weather_ai


def test_trip_forecast_uses_resolved_destination_coordinates():
    class ForecastReached(Exception):
        pass

    weather_ai._forecast_cache.clear()
    with patch.object(weather_ai, "weather_model_system", object()), \
         patch.object(weather_ai, "_geocode_openmeteo") as geocode, \
         patch.object(weather_ai, "_fetch_openmeteo_forecast", side_effect=ForecastReached) as fetch:
        with pytest.raises(ForecastReached):
            weather_ai.weather_ai_forecast(
                city="Đà Lạt", province="Lâm Đồng", days=7,
                trip_purpose=None, lat=11.9404, lon=108.4583,
            )
    geocode.assert_not_called()
    fetch.assert_called_once_with(11.9404, 108.4583, 7)


def test_unknown_vietnamese_place_does_not_fall_back_to_hanoi():
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"results": [{"country_code": "US", "latitude": 1, "longitude": 2}]}

    weather_ai._geocode_cache.clear()
    with patch.object(weather_ai.requests, "get", return_value=Response()):
        with pytest.raises(HTTPException) as exc:
            weather_ai._geocode_openmeteo("Dia diem khong co that")
    assert exc.value.status_code == 404
