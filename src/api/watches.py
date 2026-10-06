"""Server-side trip monitoring and durable in-app alerts."""
import json
import time
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from src.api.auth import get_current_user
from src.api.db import get_conn, get_trip_history_row, list_push_subscriptions_for_user
from src.api.decision import today_vietnam, validate_departure, departure_weather
from src.api.notifications import _send_push, VAPID_PRIVATE_KEY

watch_router = APIRouter(prefix='/api/watches', tags=['monitoring'])

def init_watches():
    conn = get_conn()
    try:
        conn.executescript('''CREATE TABLE IF NOT EXISTS trip_watches (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            trip_id INTEGER NOT NULL UNIQUE REFERENCES trip_history(id) ON DELETE CASCADE,
            departure_date TEXT NOT NULL, destination TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,
            province TEXT, purpose TEXT, last_score REAL, last_checked REAL, last_alert REAL, error TEXT);
            CREATE TABLE IF NOT EXISTS watch_alerts (
            id INTEGER PRIMARY KEY, watch_id INTEGER NOT NULL REFERENCES trip_watches(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, created_at REAL NOT NULL);''')
    finally:
        conn.close()

@watch_router.post('/trips/{trip_id}')
def subscribe(trip_id: int, user=Depends(get_current_user)):
    init_watches()
    trip = get_trip_history_row(trip_id, user['id'])
    if not trip:
        raise HTTPException(404, 'Không tìm thấy chuyến đi.')
    result = json.loads(trip['result_json'])
    departure = date.fromisoformat(result.get('departure_date') or today_vietnam().isoformat())
    validate_departure(departure)
    destination = result.get('to') or {}
    if destination.get('lat') is None or destination.get('lon') is None:
        raise HTTPException(422, 'Chuyến đi thiếu tọa độ điểm đến.')
    weather = result.get('weather') or {}
    news = result.get('risk') or {}
    scores = [weather.get('adjusted_risk_score', weather.get('risk_score'))]
    if news.get('data_status') == 'fresh': scores.append(news.get('risk_score'))
    initial = max((float(v) for v in scores if v is not None), default=None)
    conn = get_conn()
    try:
        conn.execute('''INSERT OR IGNORE INTO trip_watches
            (user_id,trip_id,departure_date,destination,lat,lon,province,purpose,last_score)
            VALUES (?,?,?,?,?,?,?,?,?)''', (user['id'], trip_id, departure.isoformat(), destination.get('name') or trip['destination'],
            destination['lat'], destination['lon'], destination.get('province_inferred'), trip.get('trip_purpose') or 'standard', initial))
        conn.commit()
        return dict(conn.execute('SELECT * FROM trip_watches WHERE trip_id=?', (trip_id,)).fetchone())
    finally:
        conn.close()

@watch_router.get('')
def watches(user=Depends(get_current_user)):
    init_watches(); conn = get_conn()
    try:
        return {'watches': [dict(row) for row in conn.execute('SELECT * FROM trip_watches WHERE user_id=? ORDER BY id DESC', (user['id'],))]}
    finally: conn.close()

@watch_router.get('/alerts')
def alerts(user=Depends(get_current_user)):
    init_watches(); conn = get_conn()
    try:
        return {'alerts': [dict(row) for row in conn.execute('SELECT * FROM watch_alerts WHERE user_id=? ORDER BY id DESC LIMIT 100', (user['id'],))]}
    finally: conn.close()

@watch_router.delete('/{watch_id}')
def unsubscribe(watch_id: int, user=Depends(get_current_user)):
    conn = get_conn()
    try:
        changed = conn.execute('DELETE FROM trip_watches WHERE id=? AND user_id=?', (watch_id, user['id'])).rowcount
        conn.commit()
        if not changed: raise HTTPException(404, 'Không tìm thấy theo dõi.')
        return {'deleted': True}
    finally: conn.close()

def check_watches():
    init_watches(); conn = get_conn()
    try:
        rows = [dict(row) for row in conn.execute('SELECT * FROM trip_watches WHERE departure_date>=? ORDER BY last_checked ASC LIMIT 200', (today_vietnam().isoformat(),))]
    finally: conn.close()
    checked, alerted, failed = 0, 0, 0
    for row in rows:
        now = time.time()
        try:
            weather = departure_weather(row['destination'], row['lat'], row['lon'], row['province'], row['purpose'], date.fromisoformat(row['departure_date']))
            if weather.get('error'): raise ValueError('Forecast unavailable')
            score = float(weather.get('adjusted_risk_score', weather['risk_score']))
            from src.api.utils import load_features_df, score_from_subset
            from datetime import timedelta
            frame = load_features_df()
            recent = frame[(frame['province'] == row['province']) & (frame['quality_pass'] == True)
                           & frame['pub_date'].notna()]
            recent = recent[(recent['pub_date'] >= today_vietnam() - timedelta(days=30)) & (recent['pub_date'] <= today_vietnam())]
            if not recent.empty: score = max(score, score_from_subset(recent)['overall_risk_score'])
            changed = row['last_score'] is not None and score - row['last_score'] >= 1
            should_alert = (score >= 7 or (changed and score >= 4)) and (not row['last_alert'] or now - row['last_alert'] >= 7200)
            conn = get_conn()
            try:
                conn.execute('UPDATE trip_watches SET last_score=?,last_checked=?,error=NULL WHERE id=?', (score, now, row['id']))
                if should_alert:
                    title = f"Thay đổi rủi ro: {row['destination']}"
                    body = f"Ngày đi {row['departure_date']}: điểm rủi ro hiện có {score:.1f}/10. Mở TravelShield để xem lại dự báo và nguồn tin."
                    conn.execute('INSERT INTO watch_alerts(watch_id,user_id,title,body,created_at) VALUES (?,?,?,?,?)', (row['id'], row['user_id'], title, body, now))
                    conn.execute('UPDATE trip_watches SET last_alert=? WHERE id=?', (now, row['id']))
                conn.commit()
            finally: conn.close()
            checked += 1
            if should_alert:
                alerted += 1
                if VAPID_PRIVATE_KEY:
                    for sub in list_push_subscriptions_for_user(row['user_id']):
                        if sub['watched_lat'] is not None and abs(sub['watched_lat'] - row['lat']) < .001 and abs(sub['watched_lon'] - row['lon']) < .001:
                            _send_push(sub, title, body)
        except Exception as exc:
            failed += 1; conn = get_conn()
            try:
                conn.execute('UPDATE trip_watches SET last_checked=?,error=? WHERE id=?', (now, type(exc).__name__, row['id']))
                conn.commit()
            finally: conn.close()
    return {'checked': checked, 'alerted': alerted, 'failed': failed}
