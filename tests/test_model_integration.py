"""The scores shown to travelers must use the trained model outputs safely."""
from datetime import date
import json
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.utils import _attach_news_predictions, ensure_schema, load_features_df, score_from_subset
from src.api.weather_ai import adjust_risk_for_purpose
from src.integrations.weather.main import normalize_weather_score


def test_active_news_predictions_cover_included_articles():
    articles = load_features_df(force=True)
    assert len(articles) > 0
    assert articles["p_risk_any"].notna().all()
    assert set(articles["news_model_source"]) <= {"tfidf_logreg", "phobert"}


def test_real_weather_model_loads_on_server_startup():
    from src.api.app import app

    with TestClient(app) as running_client:
        response = running_client.post("/weather/ai", json={
            "province": "Lâm Đồng", "temperature": 22, "humidity": 80,
            "precipitation": 25, "wind": 10, "pm25": 75,
            "visibility_km": 2, "uv_index": 4,
        })
    assert response.status_code == 200
    assert response.json()["detection_method"] == "AI_XGBOOST"
    assert 0 <= response.json()["risk_score"] <= 10


def test_phobert_text_is_word_segmented():
    pytest.importorskip("pyvi")
    from src.train.vietnamese import segment_for_phobert

    segmented = segment_for_phobert("Mưa lớn ở Đà Lạt khiến đường trơn trượt.")
    assert "Đà_Lạt" in segmented
    assert segment_for_phobert("") == ""


def test_mixed_rss_timezones_keep_local_article_day():
    frame = ensure_schema(pd.DataFrame([
        {"published_at": "Fri, 23 Jan 2026 00:30:00 +0700"},
        {"published_at": "Thu, 22 Jan 2026 20:00:00 +0000"},
    ]))
    assert frame["pub_date"].tolist() == [date(2026, 1, 23), date(2026, 1, 22)]


def test_phobert_probability_overrides_baseline_for_matching_article(tmp_path):
    baseline = tmp_path / "baseline.jsonl"
    phobert = tmp_path / "phobert.jsonl"
    baseline.write_text(json.dumps({"id": "one", "p_risk_any": 0.1, "model_source": "tfidf_logreg"}) + "\n", encoding="utf-8")
    phobert.write_text(json.dumps({"id": "one", "p_risk_any": 0.9, "model_source": "phobert"}) + "\n", encoding="utf-8")
    frame = ensure_schema(pd.DataFrame([
        {"id": "one", "risk_score_rule": 20, "risk_groups": ["Safety_Security"], "published_at": "2026-01-23"},
    ]))
    result = _attach_news_predictions(frame, [str(baseline), str(phobert)])
    assert result.loc[0, "p_risk_any"] == 0.9
    assert result.loc[0, "news_model_source"] == "phobert"
    assert score_from_subset(result)["overall_risk_score"] == 9


def test_news_model_reduces_false_positive_keyword_risk(tmp_path):
    predictions = tmp_path / "predictions.jsonl"
    predictions.write_text(json.dumps({"id": "one", "p_risk_any": 0.1, "model_source": "tfidf_logreg"}) + "\n", encoding="utf-8")
    frame = ensure_schema(pd.DataFrame([
        {"id": "one", "risk_score_rule": 20, "risk_groups": ["Safety_Security"], "published_at": "2026-01-23"},
    ]))
    result = score_from_subset(_attach_news_predictions(frame, [str(predictions)]))
    assert result["overall_risk_score"] == 1
    assert result["risk_assessment"]["Safety_Security"] == 0
    assert result["model_scored_articles"] == 1


def test_weather_model_score_is_normalized_for_api(client):
    payload = {
        "province": "Lâm Đồng", "temperature": 22.5, "humidity": 85,
        "precipitation": 10, "wind": 5, "pm25": 15,
        "visibility_km": 8, "uv_index": 6,
    }
    response = client.post("/weather/ai", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["detection_method"] == "AI_XGBOOST"
    assert result["model_score_0_20"] in {1.0, 4.0, 7.0, 10.0, 14.0}
    assert result["risk_score"] == round(normalize_weather_score(result["model_score_0_20"]), 2)
    assert 0 <= result["risk_score"] <= 10


def test_extreme_weather_gate_reaches_severe_api_score(client):
    payload = {
        "province": "Lâm Đồng", "temperature": 22.5, "humidity": 99,
        "precipitation": 151, "wind": 81, "pm25": 15,
        "visibility_km": 8, "uv_index": 6,
    }
    response = client.post("/weather/ai", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["detection_method"] == "SAFETY_GATE_STORM"
    assert result["risk_level"] == 5
    assert result["risk_score"] == 10
    assert result["model_score_0_20"] == 20


def test_manual_weather_api_builds_model_features(client):
    seen = {}

    class FakeModel:
        def predict(self, frame):
            seen.update(frame.iloc[0].to_dict())
            return 14.0, 4, "AI_XGBOOST"

    payload = {
        "province": "Lâm Đồng", "temperature": 22, "humidity": 80,
        "precipitation": 25, "wind": 10, "pm25": 75,
        "visibility_km": 2, "uv_index": 4,
    }
    with patch("src.api.weather_ai.weather_model_system", FakeModel()):
        response = client.post("/weather/ai", json=payload)
    assert response.status_code == 200
    assert seen["slippery_index"] == 0.4
    assert seen["visibility_block"] == 0.8
    assert seen["smog_impact"] == 0.5
    assert response.json()["risk_score"] == 7.0


def test_trip_preference_cannot_downgrade_severe_weather():
    adjusted = adjust_risk_for_purpose(7.0, "adventure", weather_data={"wind": 35})
    assert adjusted["adjusted_score"] >= 7.0


def test_weather_batch_uses_public_score_scale(client):
    class FakeModel:
        def predict_batch(self, frame):
            assert len(frame) == 1
            return [(14.0, 4, "AI_XGBOOST")]

    with patch("src.api.weather_ai.weather_model_system", FakeModel()), \
         patch("src.api.weather_ai._geocode_openmeteo", return_value={"latitude": 21.0, "longitude": 105.8, "name": "Hanoi"}), \
         patch("src.api.weather_ai._weather_cache_get", return_value=None), \
         patch("src.api.weather_ai._fetch_openmeteo_weather", return_value={"elevation": 0}), \
         patch("src.api.weather_ai.transform_openmeteo_to_ai_format", return_value={"temperature": 25}):
        response = client.post("/weather/ai/batch", json={"cities": ["Hanoi"]})
    assert response.status_code == 200
    assert response.json()["results"][0]["risk_score"] == 7.0


def test_trip_severe_weather_remains_no_go_for_adventure(client):
    from src.api import app as api_module

    class FakeModel:
        def predict(self, frame):
            return 14.0, 4, "AI_XGBOOST"

    traffic = {"distance_km": 300, "time_normal_min": 300, "time_traffic_min": 320,
               "speed_kmh": 60, "status": "light", "status_emoji": "🟢"}
    weather_input = {"temperature": 22, "humidity": 80, "precipitation": 0,
                     "wind": 35, "visibility_km": 10, "uv_index": 3}
    api_module._trip_cache.clear()
    with patch("src.api.app.load_features_df", return_value=pd.DataFrame()), \
         patch("src.api.app.search_location_google", return_value=(11.94, 108.44, "Đà Lạt, Lâm Đồng, Việt Nam")), \
         patch("src.api.app.check_route_traffic_google", return_value=traffic), \
         patch("src.api.app.ensure_route_polyline", return_value=None), \
         patch("src.api.app.weather_model_system", FakeModel()), \
         patch("src.api.app._weather_cache_get", return_value=None), \
         patch("src.api.app._fetch_openmeteo_weather", return_value={"elevation": 0}), \
         patch("src.api.app.transform_openmeteo_to_ai_format", return_value=weather_input):
        response = client.get("/trip", params={
            "destination": "Đà Lạt severe adventure test", "lat": "10.77", "lon": "106.69",
            "trip_purpose": "adventure",
        })
    assert response.status_code == 200
    result = response.json()
    assert result["weather"]["risk_score"] == 7.0
    assert result["weather"]["adjusted_risk_score"] >= 7.0
    assert result["recommendation"].startswith("❌ KHÔNG NÊN ĐI")


def test_trip_marks_old_news_as_stale(client):
    from src.api import app as api_module

    old_news = pd.DataFrame([{
        "id": "old", "province": "Lâm Đồng", "quality_pass": True,
        "risk_groups": ["Safety_Security"], "risk_score_rule": 20.0,
        "risk_score_effective": 20.0, "pub_date": date(2020, 1, 1),
    }])
    traffic = {
        "distance_km": 300, "time_normal_min": 300, "time_traffic_min": 320,
        "speed_kmh": 60, "status": "light", "status_emoji": "🟢",
    }
    api_module._trip_cache.clear()
    with patch("src.api.app.load_features_df", return_value=old_news), \
         patch("src.api.app.search_location_google", return_value=(11.94, 108.44, "Đà Lạt, Lâm Đồng, Việt Nam")), \
         patch("src.api.app.check_route_traffic_google", return_value=traffic), \
         patch("src.api.app.ensure_route_polyline", return_value=None), \
         patch("src.api.app.weather_model_system", None):
        response = client.get("/trip", params={"destination": "Đà Lạt stale data test", "lat": "10.77", "lon": "106.69"})
    assert response.status_code == 200
    result = response.json()
    assert result["risk"]["data_status"] == "stale"
    assert result["risk"]["risk_score"] is None
    assert result["risk"]["historical_risk_score"] == 10
    assert result["recommendation"].startswith("⚠️ CẨN THẬN")


def test_trip_current_news_score_excludes_old_articles(client):
    from src.api import app as api_module

    news = pd.DataFrame([
        {"id": "old", "province": "Lâm Đồng", "quality_pass": True,
         "risk_groups": ["Safety_Security"], "risk_score_rule": 20.0,
         "risk_score_effective": 20.0, "pub_date": date(2020, 1, 1)},
        {"id": "new", "province": "Lâm Đồng", "quality_pass": True,
         "risk_groups": [], "risk_score_rule": 0.0,
         "risk_score_effective": 0.0, "pub_date": date.today()},
    ])
    traffic = {"distance_km": 300, "time_normal_min": 300, "time_traffic_min": 320,
               "speed_kmh": 60, "status": "light", "status_emoji": "🟢"}
    api_module._trip_cache.clear()
    with patch("src.api.app.load_features_df", return_value=news), \
         patch("src.api.app.search_location_google", return_value=(11.94, 108.44, "Đà Lạt, Lâm Đồng, Việt Nam")), \
         patch("src.api.app.check_route_traffic_google", return_value=traffic), \
         patch("src.api.app.ensure_route_polyline", return_value=None), \
         patch("src.api.app.weather_model_system", None):
        response = client.get("/trip", params={"destination": "Đà Lạt recent-only test", "lat": "10.77", "lon": "106.69"})
    assert response.status_code == 200
    risk = response.json()["risk"]
    assert risk["data_status"] == "fresh"
    assert risk["num_articles"] == 1
    assert risk["historical_num_articles"] == 2
    assert risk["risk_score"] == 0
    assert risk["historical_risk_score"] == 5
