"""Date-specific weather selection and actionable explanations."""
from datetime import date, datetime, timedelta, timezone
from fastapi import HTTPException
from src.api.weather_ai import weather_ai_forecast

def today_vietnam():
    return datetime.now(timezone(timedelta(hours=7))).date()

def validate_departure(value):
    if value and not 0 <= (value - today_vietnam()).days <= 15:
        raise HTTPException(422, "Ngày đi phải nằm trong 16 ngày dự báo, tính từ hôm nay.")

def departure_weather(destination, lat, lon, province, purpose, departure):
    forecast = weather_ai_forecast(city=destination, lat=lat, lon=lon, province=province, days=16, trip_purpose=purpose)
    selected = next((row for row in forecast['daily'] if row['date'] == departure.isoformat()), None)
    if not selected:
        return {"error": "Chưa có dự báo cho ngày khởi hành.", "date": departure.isoformat()}
    return {**selected, "weather_provider": forecast['weather_provider'], "assessment_basis": "departure_forecast"}

def explain(result):
    weather, traffic, news = (result.get(k) or {} for k in ('weather', 'traffic', 'risk'))
    findings, actions, missing = [], [], []
    if weather.get('error') or not weather:
        missing.append('weather'); findings.append('Chưa có dữ liệu thời tiết cho ngày đi.')
        actions.append('Tra cứu lại dự báo trước khi quyết định khởi hành.')
    else:
        score = weather.get('adjusted_risk_score', weather.get('risk_score'))
        findings.append(f"Thời tiết ngày đi: {score}/10. {weather.get('message', '')}")
        if score is not None and float(score) >= 4:
            actions.append('Cân nhắc đổi ngày đi; xem cảnh báo địa phương và chuẩn bị phương án dự phòng.')
    if not traffic.get('traffic_available'):
        missing.append('live_traffic'); actions.append('Kiểm tra giao thông và chỉ đường ngay trước lúc xuất phát.')
    if traffic.get('route_available') is False:
        missing.append('route')
    if news.get('data_status') != 'fresh':
        missing.append('recent_news')
        findings.append(f"Tin tức: {news.get('data_status', 'no_data')}; bài gần nhất {news.get('latest_article_date') or 'chưa có'}.")
        actions.append('Kiểm tra nguồn tin mới và thông báo cơ quan chức năng tại điểm đến.')
    else:
        findings.append(f"Có {news.get('num_articles', 0)} bài mới; điểm tin tức {news.get('risk_score')}/10.")
    if result.get('departure_date') and result['departure_date'] > today_vietnam().isoformat():
        findings.append('Giao thông và tin tức phản ánh lúc tra cứu; điều kiện có thể thay đổi trước ngày đi.')
        actions.append('Đánh giá lại trước ngày khởi hành hoặc bật theo dõi thay đổi.')
    return {'findings': findings, 'actions': list(dict.fromkeys(actions or ['Theo dõi diễn biến mới và đánh giá lại trước lúc đi.'])),
            'missing_sources': missing, 'coverage': 'partial' if missing else 'complete',
            'news_age_days': (today_vietnam() - date.fromisoformat(news['latest_article_date'])).days if news.get('latest_article_date') else None,
            'basis': 'departure_forecast' if result.get('departure_date') else 'current_conditions'}
