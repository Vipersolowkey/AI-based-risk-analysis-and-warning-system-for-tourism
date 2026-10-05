import urllib.parse


def test_risk_known_province(client):
    place = urllib.parse.quote("TP Hồ Chí Minh")
    resp = client.get(f"/risk?place={place}")
    assert resp.status_code == 200
    data = resp.json()
    assert "overall_risk_score" in data
    assert "num_articles" in data
    assert data["num_articles"] >= 0
    assert data["model_scored_articles"] > 0
    assert "tfidf_logreg" in data["news_model_source"]
    assert "latest_article_date" in data


def test_risk_compare(client):
    places = urllib.parse.quote("TP Hồ Chí Minh,Hà Nội,Đà Nẵng")
    resp = client.get(f"/risk/compare?places={places}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 3
    assert len(data["results"]) == 3


def test_risk_compare_too_many_places(client):
    places = ",".join(f"Province{i}" for i in range(25))
    resp = client.get(f"/risk/compare?places={places}")
    assert resp.status_code == 422


def test_risk_trend_known_province(client):
    place = urllib.parse.quote("Hà Nội")
    resp = client.get(f"/risk/trend?place={place}")
    assert resp.status_code == 200
    data = resp.json()
    assert "trend" in data
    assert isinstance(data["trend"], list)


def test_map_points(client):
    resp = client.get("/map/points")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["points"]) > 0
    assert "province" in data["points"][0]


def test_map_heat(client):
    resp = client.get("/map/heat")
    assert resp.status_code == 200
    assert "points" in resp.json()


def test_risk_events_use_source_articles_without_benign_headlines(client):
    resp = client.get("/risk/events", params={"place": "Lâm Đồng", "limit": 12})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["count"] == len(payload["events"])
    assert len({event["id"] for event in payload["events"]}) == payload["count"]
    assert all(event["url"].startswith("http") for event in payload["events"])
    assert all("Đại hội" not in event["title"] for event in payload["events"])


def test_risk_events_headline_filter():
    from src.api.app import _EXPLICIT_RISK_HEADLINE, _headline_mentions_place

    assert _EXPLICIT_RISK_HEADLINE.search("Cảnh báo mưa lớn và sạt lở ở Lâm Đồng")
    assert _EXPLICIT_RISK_HEADLINE.search("Công an giúp người dân thoát bẫy lừa đảo")
    assert not _EXPLICIT_RISK_HEADLINE.search("Đại hội XIV tạo động lực phát triển")
    assert not _EXPLICIT_RISK_HEADLINE.search("Chạy bộ gây quỹ tại Đà Lạt")
    assert _headline_mentions_place("TP.HCM khắc phục sạt lở kênh Tàu Hủ", "TP Hồ Chí Minh")
    assert _headline_mentions_place("Mưa lớn ở Đà Lạt", "Lâm Đồng")
    assert not _headline_mentions_place("Tin tai nạn giao thông hôm nay", "Lâm Đồng")
