# src/api/app.py
"""
Vietnam Travel Risk API — FastAPI application.
Endpoints only. Logic lives in config.py, utils.py, routes.py, weather_ai.py.
"""
import os
import sys

# Windows console defaults to cp1252, which crashes on print() of Vietnamese
# diacritics/emoji used throughout this codebase. Force UTF-8 at process start
# so this works regardless of how uvicorn is launched (dev, Docker, CI).
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
import math
import re
import unicodedata
import time
import asyncio
import traceback
from html import unescape
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from datetime import date, timedelta, datetime, timezone
from typing import Optional, Dict
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import numpy as np
from fastapi import FastAPI, Query, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import joblib

# ---- pickle compat for weather model ----
from src.integrations.weather.main import HybridSafetyPredictor, WeatherPreprocessor, map_risk_level_v17, normalize_weather_score
sys.modules['__main__'].WeatherPreprocessor = WeatherPreprocessor
sys.modules['__main__'].map_risk_level_v17 = map_risk_level_v17

# ---- internal modules ----
from src.api.config import (
    FEATURES_PATH, PROVINCES_CFG, WEATHER_MODEL_PATH,
    WEATHER_MODEL_FEATURES_PATH,
    TRACKASIA_BASE, TRACKASIA_KEY, RISK_GROUPS, NEWS_RISK_MAX_AGE_DAYS,
)
from src.api.utils import (
    load_features_df, resolve_place, score_from_subset,
    load_provinces_yaml, load_province_centroids,
    infer_province_from_text, format_minutes_human,
)
from src.api.routes import ensure_route_polyline
from src.api.weather_ai import (
    weather_router, register_weather_model,
    _weather_cache, _geocode_cache, _WEATHER_CACHE_TTL, _GEOCODE_CACHE_TTL,
    _forecast_cache, _FORECAST_CACHE_TTL,
    _geocode_openmeteo, _fetch_openmeteo_weather, _weather_cache_key,
    _weather_cache_get, _weather_cache_set,
    transform_openmeteo_to_ai_format, MSG_MAP,
    adjust_risk_for_purpose,
)
from src.integrations.traffic.serpapi_service import (
    search_location_google,
    check_route_traffic_google,
    unavailable_route,
    _serpapi_geo_cache, _SERPAPI_GEO_CACHE_TTL,
)
from src.api.db import init_db, save_trip_history, list_trip_history, delete_trip_history
from src.api.auth import auth_router, get_current_user, get_current_user_optional
from src.api.notifications import notification_router
from src.api.decision import validate_departure, departure_weather, explain

# ============================================================
# Thread pool for parallel I/O in async endpoints
# ============================================================
_executor = ThreadPoolExecutor(max_workers=8)


class _NumpySafeEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy/pandas types automatically."""
    def default(self, obj):
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (pd.Timestamp,)):
            return obj.isoformat()
        if isinstance(obj, (pd.Series,)):
            return obj.tolist()
        if getattr(type(obj), '__module__', '').startswith('numpy'):
            try:
                return obj.item()
            except (AttributeError, ValueError):
                return str(obj)
        return super().default(obj)


def _safe_json_response(data: dict, status_code: int = 200) -> JSONResponse:
    """Return a JSONResponse using our numpy-safe encoder.
    This completely bypasses FastAPI's jsonable_encoder."""
    body = json.dumps(data, cls=_NumpySafeEncoder, ensure_ascii=False)
    return JSONResponse(content=json.loads(body), status_code=status_code)


def _sanitize_for_json(obj):
    """Recursively convert numpy/pandas types to native Python types
    so FastAPI's jsonable_encoder / json.dumps won't choke."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    # Check numpy types early — must come before generic number checks
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if isinstance(obj, (pd.Series,)):
        return obj.tolist()
    # If the object's module is 'numpy', force conversion
    if getattr(type(obj), '__module__', '').startswith('numpy'):
        try:
            return obj.item()
        except (AttributeError, ValueError):
            return str(obj)
    # Native Python types pass through
    if isinstance(obj, (str, int, float, bool)):
        return obj
    # Last resort: try to convert to string
    try:
        json.dumps(obj)  # test if json-serializable
        return obj
    except (TypeError, ValueError):
        return str(obj)


# ============================================================
# APP
# ============================================================
@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_weather_model()
    init_database()
    from src.api.news_refresh import init_news
    from src.api.watches import init_watches
    from src.api.background import background_loop
    init_news(); init_watches()
    worker = asyncio.create_task(background_loop()) if os.getenv('BACKGROUND_JOBS_ENABLED', 'true').lower() == 'true' else None
    try:
        yield
    finally:
        if worker:
            worker.cancel()
            from contextlib import suppress
            with suppress(asyncio.CancelledError): await worker


app = FastAPI(title="TravelShield API", version="3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Request logging middleware ----
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    if elapsed > 1.0:  # only log slow requests (>1s)
        print(f"[SLOW] {request.method} {request.url.path} → {response.status_code} in {elapsed:.2f}s")
    return response

weather_model_system = None


def load_weather_model():
    global weather_model_system
    try:
        model = joblib.load(WEATHER_MODEL_PATH)
        # If the pkl contains a dict (legacy), extract the pipeline; otherwise use directly
        if isinstance(model, dict):
            pipeline = model.get("pipeline", model.get("model", model))
        else:
            pipeline = model
        # Load feature names from model_features.json
        feature_names = None
        if os.path.exists(WEATHER_MODEL_FEATURES_PATH):
            with open(WEATHER_MODEL_FEATURES_PATH, "r", encoding="utf-8") as f:
                feature_names = json.load(f)
            print(f"[Weather AI] Loaded {len(feature_names)} feature names: {feature_names}")
        else:
            print(f"[Weather AI] Warning: {WEATHER_MODEL_FEATURES_PATH} not found, using model defaults")
        weather_model_system = HybridSafetyPredictor(pipeline, feature_names=feature_names)
        print("[Weather AI] Model loaded successfully.")
        register_weather_model(weather_model_system)
    except Exception as e:
        print(f"[Weather AI] Failed to load model: {e}")



# Note: the features DataFrame is intentionally NOT eagerly preloaded at
# startup — on memory-constrained hosts (e.g. Render's free 512MB tier),
# loading the weather model + this DataFrame simultaneously at startup can
# exceed the memory limit and crash the process before it can serve any
# requests. load_features_df() (in utils.py) lazy-loads and caches on the
# first request that actually needs it (/risk, /trip, etc.), so cold start
# is a bit slower on the very first such request instead.


def init_database():
    """Create users/trip_history/push_subscriptions tables if they don't exist."""
    try:
        init_db()
        print("[Startup] SQLite app database ready.")
    except Exception as e:
        print(f"[Startup] Failed to init database: {e}")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    print(f"\n[API UNHANDLED] path={request.url.path} err={repr(exc)}\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error"},
    )


# ============================================================
# DEBUG / HEALTH
# ============================================================
@app.get("/health")
def health():
    return {"ok": True}


@app.get("/debug/where")
def debug_where():
    return {
        "project_root": os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
        "features_path": FEATURES_PATH,
        "features_exists": os.path.exists(FEATURES_PATH),
        "features_size": os.path.getsize(FEATURES_PATH) if os.path.exists(FEATURES_PATH) else None,
        "provinces_yaml": PROVINCES_CFG,
        "provinces_exists": os.path.exists(PROVINCES_CFG),
        "trackasia_base": TRACKASIA_BASE,
        "trackasia_key_set": bool(TRACKASIA_KEY),
        "cwd": os.getcwd(),
        "python": sys.executable,
    }


@app.get("/debug/sample")
def debug_sample(n: int = 5):
    if not os.path.exists(FEATURES_PATH):
        raise HTTPException(status_code=404, detail=f"Missing: {FEATURES_PATH}")
    sample = []
    with open(FEATURES_PATH, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            if len(sample) >= n:
                break
            line = line.strip()
            if not line:
                continue
            try:
                sample.append(json.loads(line))
            except Exception as e:
                return {"error": "bad_json_line", "line_no": i, "exception": str(e), "line_head": line[:200]}
    return {"sample": sample}


@app.get("/debug/stats")
def debug_stats(reload: bool = False):
    df = load_features_df(force=reload)
    return {
        "rows": int(len(df)),
        "columns": list(df.columns),
        "province_top": df["province"].fillna("NULL").value_counts().head(10).to_dict(),
    }


# ============================================================
# RISK
# ============================================================
@app.get("/risk")
def risk_summary(
    place: str = Query(...),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    quality_only: bool = True,
    reload: bool = False,
):
    df = load_features_df(force=reload)
    resolved = resolve_place(place)

    df_sub = df[df["province"].fillna("") == resolved].copy()
    if quality_only:
        df_sub = df_sub[df_sub["quality_pass"] == True]
    if start_date:
        df_sub = df_sub[df_sub["pub_date"].notna() & (df_sub["pub_date"] >= start_date)]
    if end_date:
        df_sub = df_sub[df_sub["pub_date"].notna() & (df_sub["pub_date"] <= end_date)]

    return {"place": place, "resolved": resolved, **score_from_subset(df_sub)}


_EXPLICIT_RISK_HEADLINE_TERMS = (
    "bão", "áp thấp", "mưa lớn", "mưa đá", "lũ", "lụt", "ngập",
    "sạt lở", "sóng thần", "động đất", "nắng nóng", "hạn hán",
    "tai nạn", "va chạm", "cháy", "hỏa hoạn", "phát nổ", "nổ súng",
    "đuối nước", "mất tích", "thương vong", "tử vong", "thiệt mạng",
    "sập cầu", "sập nhà", "sét đánh", "cướp", "trộm", "lừa đảo",
    "lừa", "tấn công", "hành hung", "ngộ độc", "dịch bệnh",
    "ô nhiễm", "bụi mịn", "kẹt xe", "ùn tắc", "cấm đường",
    "đường bị chặn", "phong tỏa", "sơ tán", "mất điện", "nguy hiểm",
)
_EXPLICIT_RISK_HEADLINE = re.compile(
    r"\b(?:" + "|".join(re.escape(term) for term in _EXPLICIT_RISK_HEADLINE_TERMS) + r")\b",
    re.IGNORECASE,
)


def _headline_mentions_place(title: str, place: str) -> bool:
    def plain(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value.casefold()).replace("đ", "d")
        return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in normalized if not unicodedata.combining(c))).strip()

    headline = f" {plain(title)} "
    canonical = plain(place)
    aliases = {
        "tp ho chi minh": ("tp hcm", "tphcm", "ho chi minh", "sai gon"),
        "ha noi": ("hanoi",),
        "lam dong": ("da lat",),
        "khanh hoa": ("nha trang",),
        "da nang": ("danang",),
        "ba ria vung tau": ("vung tau",),
    }
    return any(f" {name} " in headline for name in (canonical, *aliases.get(canonical, ())))


@app.get("/risk/events")
def risk_events(
    place: str = Query(...),
    limit: int = Query(12, ge=1, le=50),
):
    """Return source articles whose headlines explicitly mention a risk event.

    The model's broad positive label also includes many benign articles. A
    headline filter keeps the event list from presenting those as incidents.
    The separate /risk summary retains its existing scoring contract.
    """
    df = load_features_df(force=False)
    resolved = resolve_place(place)
    rows = df[(df["province"].fillna("") == resolved) & (df["quality_pass"] == True)].copy()
    rows = rows[rows["risk_any"] == True]
    if "p_risk_any" in rows:
        rows = rows[(rows["p_risk_any"].isna()) | (rows["p_risk_any"] >= 0.5)]
    rows = rows[rows["title"].fillna("").map(
        lambda title: bool(_EXPLICIT_RISK_HEADLINE.search(unescape(unescape(str(title)))))
        and _headline_mentions_place(unescape(unescape(str(title))), resolved)
    )]
    rows = rows.sort_values(["pub_date", "id"], ascending=[False, False], na_position="last").drop_duplicates("id")
    events = []
    for _, row in rows.head(limit).iterrows():
        url = str(row.get("url") or "")
        published = row.get("pub_date")
        score = row.get("risk_score_effective")
        events.append({
            "id": str(row.get("id")),
            "title": unescape(unescape(str(row.get("title") or "Không có tiêu đề"))),
            "date": published.isoformat() if pd.notna(published) else None,
            "source": urlparse(url).netloc.removeprefix("www.") if url else None,
            "url": url if url.startswith(("https://", "http://")) else None,
            "severity": str(row.get("severity_bucket")) if pd.notna(row.get("severity_bucket")) else None,
            "risk_score": round(float(score) / 2, 1) if pd.notna(score) else None,
            "risk_groups": list(row.get("risk_groups") or []),
        })
    return {"place": place, "resolved": resolved, "count": len(events), "events": events}


@app.get("/risk/compare")
def risk_compare(
    places: str = Query(..., description="Comma-separated list of places, e.g. 'Đà Nẵng,Hà Nội,Đà Lạt'"),
    quality_only: bool = True,
    reload: bool = False,
):
    """Compare risk scores for multiple provinces at once."""
    df = load_features_df(force=reload)
    place_list = [p.strip() for p in places.split(",") if p.strip()]
    if not place_list:
        raise HTTPException(status_code=422, detail="places is required (comma-separated)")
    if len(place_list) > 20:
        raise HTTPException(status_code=422, detail="Max 20 places per request")

    results = []
    for place in place_list:
        resolved = resolve_place(place)
        df_sub = df[df["province"].fillna("") == resolved].copy()
        if quality_only:
            df_sub = df_sub[df_sub["quality_pass"] == True]
        score = score_from_subset(df_sub)
        results.append({"place": place, "resolved": resolved, **score})

    # Sort by risk score descending
    results.sort(key=lambda x: x.get("overall_risk_score", 0), reverse=True)
    return {"count": len(results), "results": results}


@app.get("/risk/trend")
def risk_trend(
    place: str = Query(...),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    quality_only: bool = True,
    reload: bool = False,
    window_days: int = 60,
):
    df = load_features_df(force=reload)
    resolved = resolve_place(place)

    df_sub = df[df["province"].fillna("") == resolved].copy()
    if quality_only:
        df_sub = df_sub[df_sub["quality_pass"] == True]

    if not start_date and not end_date:
        today = date.today()
        start_date = today - timedelta(days=window_days)
        end_date = today

    if start_date:
        df_sub = df_sub[df_sub["pub_date"].notna() & (df_sub["pub_date"] >= start_date)]
    if end_date:
        df_sub = df_sub[df_sub["pub_date"].notna() & (df_sub["pub_date"] <= end_date)]

    if df_sub.empty:
        return {"place": place, "resolved": resolved, "trend": []}

    g = (
        df_sub.groupby("pub_date")
        .agg(num_articles=("id", "count"), avg_rule=("risk_score_effective", "mean"))
        .reset_index()
    )
    g["risk_score"] = (g["avg_rule"] / 20.0 * 10.0).clip(0, 10).round().astype(int)

    trend = [
        {"date": str(r["pub_date"]), "num_articles": int(r["num_articles"]), "risk_score": int(r["risk_score"])}
        for _, r in g.sort_values("pub_date").iterrows()
    ]
    return {"place": place, "resolved": resolved, "trend": trend}


# ============================================================
# GPS (DEV)
# ============================================================
@app.get("/gps", response_class=HTMLResponse)
def gps_page():

    return """<!DOCTYPE html><html><body style="font-family:sans-serif;text-align:center;padding:40px">

<h2>Đang lấy GPS...</h2><p id="out"></p>

<script>

navigator.geolocation.getCurrentPosition(

  p=>{const lat=p.coords.latitude,lon=p.coords.longitude,acc=p.coords.accuracy;

    document.getElementById("out").innerText=`lat=${lat}, lon=${lon}, acc=${acc}`;

    fetch(`/gps/result?lat=${lat}&lon=${lon}&acc=${acc}`).then(r=>r.json()).then(console.log);},

  e=>{document.getElementById("out").innerText="GPS Error: "+e.message;},

  {enableHighAccuracy:true,timeout:10000});

</script></body></html>"""

@app.get("/gps/result")
def gps_result(lat: float, lon: float, acc: float = 0.0):
    return {"lat": lat, "lon": lon, "acc": acc}


# ============================================================
# TRIP CACHE  (in-memory, TTL-based)
# ============================================================
_TRIP_CACHE_TTL = 300  # 5 minutes
_trip_cache: Dict[str, dict] = {}  # key -> {"ts": float, "response": dict}


def _trip_cache_key(destination: str, lat: float, lon: float, purpose: str = "standard") -> str:
    """Round GPS to ~500m precision so nearby positions hit same cache."""
    dest_norm = destination.strip().lower()
    return f"{dest_norm}|{lat:.3f}|{lon:.3f}|{purpose}"


def _trip_cache_get(key: str) -> Optional[dict]:
    entry = _trip_cache.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > _TRIP_CACHE_TTL:
        _trip_cache.pop(key, None)
        return None
    return entry["response"]


def _trip_cache_set(key: str, response: dict):
    # Evict old entries to prevent memory leak (keep max 200)
    if len(_trip_cache) > 200:
        cutoff = time.time() - _TRIP_CACHE_TTL
        expired = [k for k, v in _trip_cache.items() if v["ts"] < cutoff]
        for k in expired:
            _trip_cache.pop(k, None)
    _trip_cache[key] = {"ts": time.time(), "response": response}


# ============================================================
# TRIP  (async + parallel I/O)
# ============================================================
@app.get("/trip")
async def trip_check(
    destination: str = Query(...),
    lat: str = Query(...),
    lon: str = Query(...),
    trip_purpose: Optional[str] = Query("standard", description="Trip purpose: standard, dating, family, adventure, solo"),
    departure_date: Optional[date] = Query(None),
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    import urllib.parse

    # ---- Global try/except: prints full traceback on ANY crash ----
    try:
        # ---- Robust input parsing ----
        destination = urllib.parse.unquote(destination).strip()
        trip_purpose = (trip_purpose or "standard").strip().lower()
        validate_departure(departure_date)

        try:
            lat_f = float(lat.replace(",", "."))
            lon_f = float(lon.replace(",", "."))
        except Exception:
            raise HTTPException(status_code=422, detail="lat/lon must be numeric")
        if not (math.isfinite(lat_f) and math.isfinite(lon_f) and -90 <= lat_f <= 90 and -180 <= lon_f <= 180):
            raise HTTPException(status_code=422, detail="lat/lon must be valid coordinates")

        # --- Check cache first ---
        cache_key = _trip_cache_key(destination, lat_f, lon_f, trip_purpose)
        from src.api.news_refresh import news_revision
        cache_key += f"|{departure_date or ''}|{news_revision()}"
        cached = _trip_cache_get(cache_key)
        if cached:
            cached = dict(cached)
            if current_user:
                try:
                    cached["history_id"] = save_trip_history(current_user["id"], destination, lat_f, lon_f, trip_purpose, cached)
                except Exception as e:
                    print(f"[/trip] WARNING: failed to save cached trip history: {e}")
            return _safe_json_response({**cached, "_cached": True})

        loop = asyncio.get_event_loop()

        # 1) Resolve destination (geocode) — run in thread pool
        try:
            dest_lat, dest_lon, dest_name = await loop.run_in_executor(
                _executor, search_location_google, destination
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Lỗi tìm vị trí: {e}")
        if dest_lat is None or dest_lon is None or not dest_name:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy điểm đến: {destination}")

        # 2) Pre-load features DF (from cache, very fast after startup)
        try:
            df = load_features_df(force=False)
        except Exception as e:
            print(f"[/trip] WARNING: news features unavailable: {e}")
            df = pd.DataFrame()

        prov = None
        try:
            prov = infer_province_from_text(dest_name)
        except Exception:
            pass

        # Determine if destination matches a known map-marker province
        matched_province = None
        if prov:
            try:
                centroids = load_province_centroids()
                if prov in centroids:
                    matched_province = prov
            except Exception:
                pass

        # 3) Run traffic, weather, and risk scoring IN PARALLEL
        async def fetch_traffic():
            try:
                return await loop.run_in_executor(
                    _executor, check_route_traffic_google,
                    "Vị trí hiện tại", dest_name, lat_f, lon_f, dest_lat, dest_lon,
                )
            except Exception as exc:
                print(f"[/trip] Traffic provider unavailable: {type(exc).__name__}")
                return unavailable_route()

        async def fetch_weather():
            try:
                if not weather_model_system or not dest_name:
                    return None
                w_cache_key = _weather_cache_key(dest_name)
                cached_w = _weather_cache_get(w_cache_key)
                if cached_w:
                    om_data = cached_w
                else:
                    om_data = await loop.run_in_executor(
                        _executor, _fetch_openmeteo_weather, float(dest_lat), float(dest_lon)
                    )
                    _weather_cache_set(w_cache_key, om_data)

                province_label = prov or dest_name
                geo_info = {
                    "elevation": om_data.get("elevation", 0.0),
                    "latitude": dest_lat,
                    "longitude": dest_lon,
                }
                purpose = trip_purpose or "standard"
                ai_input = transform_openmeteo_to_ai_format(om_data, province=province_label, geo=geo_info, purpose=purpose)
                _wdf = pd.DataFrame([ai_input])
                w_score, w_level, w_method = weather_model_system.predict(_wdf)

                # ---- Type safety: ensure w_score is a float ----
                w_score = float(w_score)

                normalized_w_score = normalize_weather_score(w_score)
                w_result = {
                    "risk_level": int(w_level),
                    "risk_score": round(normalized_w_score, 2),
                    "model_score_0_20": round(w_score, 2),
                    "message": MSG_MAP.get(int(w_level), "Unknown"),
                    "detection_method": w_method,
                    "temperature": ai_input.get("temperature"),
                    "humidity": ai_input.get("humidity"),
                    "precipitation": ai_input.get("precipitation"),
                    "wind": ai_input.get("wind"),
                    "visibility_km": ai_input.get("visibility_km"),
                    "uv_index": ai_input.get("uv_index"),
                }

                # Trip purpose adjustment (always runs — defaults to "standard")
                purpose = trip_purpose or "standard"
                try:
                    adj = adjust_risk_for_purpose(normalized_w_score, purpose, weather_data=ai_input)
                    w_result["trip_purpose"] = purpose
                    w_result["purpose_label"] = adj["purpose_label"]
                    w_result["adjusted_risk_score"] = adj["adjusted_score"]
                    w_result["adjusted_reason"] = adj["adjusted_reason"]
                except Exception as adj_err:
                    print(f"[/trip fetch_weather] ERROR in adjust_risk_for_purpose: {adj_err}")
                    print(traceback.format_exc())
                    w_result["trip_purpose"] = purpose
                    w_result["purpose_label"] = ""
                    w_result["adjusted_risk_score"] = round(normalized_w_score, 2)
                    w_result["adjusted_reason"] = f"Lỗi điều chỉnh: {adj_err}"
                return w_result
            except Exception as e:
                print(f"[/trip fetch_weather] ERROR: {e}")
                print(traceback.format_exc())
                return {"error": str(e)}

        def compute_risk():
            risk_score, risk_num_articles = None, 0
            historical_num_articles = 0
            historical_risk_score, latest_article_date = None, None
            risk_data_status = "no_data"
            risk_assessment: Dict[str, int] = {g: 0 for g in RISK_GROUPS}
            model_source, model_scored_articles = "rules", 0
            if prov and not df.empty and {"province", "quality_pass"}.issubset(df.columns):
                df_sub = df[(df["province"].fillna("") == prov) & (df["quality_pass"] == True)]
                historical = score_from_subset(df_sub)
                historical_num_articles = int(historical["num_articles"])
                latest_article_date = historical["latest_article_date"]
                model_source = historical["news_model_source"]
                if historical_num_articles:
                    historical_risk_score = int(historical["overall_risk_score"])
                    risk_data_status = "stale"

                if "pub_date" in df_sub.columns:
                    today = date.today()
                    recent_start = today - timedelta(days=NEWS_RISK_MAX_AGE_DAYS)
                    df_sub = df_sub[
                        df_sub["pub_date"].notna()
                        & (df_sub["pub_date"] >= recent_start)
                        & (df_sub["pub_date"] <= today)
                    ]
                else:
                    df_sub = df_sub.iloc[0:0]
                recent = score_from_subset(df_sub)
                risk_num_articles = int(recent["num_articles"])
                if risk_num_articles:
                    risk_score = int(recent["overall_risk_score"])
                    risk_assessment = recent["risk_assessment"]
                    model_source = recent["news_model_source"]
                    model_scored_articles = recent["model_scored_articles"]
                    risk_data_status = "fresh"
            return (risk_score, risk_num_articles, risk_assessment, model_source,
                    model_scored_articles, historical_risk_score, historical_num_articles,
                    latest_article_date, risk_data_status)

        # Fire all three tasks concurrently
        traffic_task = asyncio.create_task(fetch_traffic())
        weather_task = asyncio.create_task(fetch_weather())
        risk_future = loop.run_in_executor(_executor, compute_risk)

        traffic, weather_info, (risk_score, risk_num_articles, risk_assessment, model_source,
                                model_scored_articles, historical_risk_score, historical_num_articles,
                                latest_article_date,
                                risk_data_status) = await asyncio.gather(
            traffic_task, weather_task, risk_future
        )

        # Routing providers are optional. Weather and news remain useful if they fail.
        current_weather = weather_info
        if departure_date:
            try:
                weather_info = await loop.run_in_executor(_executor, departure_weather,
                    dest_name, float(dest_lat), float(dest_lon), prov, trip_purpose, departure_date)
            except Exception:
                weather_info = {"error": "Không lấy được dự báo cho ngày khởi hành.", "date": departure_date.isoformat()}
        if not isinstance(traffic, dict) or not traffic or traffic.get("error"):
            traffic = unavailable_route()
        if traffic.get("route_available") is not False:
            await loop.run_in_executor(
                _executor, ensure_route_polyline, traffic, lat_f, lon_f, float(dest_lat), float(dest_lon)
            )

        # 5) Recommendation (enhanced with weather + trip purpose)
        recommendation = "✅ NÊN ĐI"
        reasons = []
        caution_reasons = []
        if "🔴" in str(traffic.get("status_emoji") or "") or traffic.get("status") == "heavy":
            reasons.append("kẹt xe nặng")
        if traffic.get("route_available") is False:
            caution_reasons.append("chưa lấy được tuyến đường; cần kiểm tra chỉ đường trước khi đi")
        elif traffic.get("traffic_available") is False:
            caution_reasons.append("chưa có dữ liệu giao thông trực tiếp; thời gian đi chỉ là ước tính")
        if isinstance(risk_score, int) and risk_score >= 7:
            reasons.append("rủi ro báo chí cao")
        if risk_data_status == "stale":
            caution_reasons.append("tin tức rủi ro chưa được cập nhật")
        elif risk_data_status == "no_data":
            caution_reasons.append("chưa có dữ liệu tin tức cho điểm đến")

        # Use adjusted risk score if trip_purpose provided, else base score
        w_risk_score = None
        if weather_info and not weather_info.get("error"):
            adj_val = weather_info.get("adjusted_risk_score")
            w_risk_score = adj_val if adj_val is not None else weather_info.get("risk_score", 0)
            try:
                w_risk_score = float(w_risk_score)
            except (TypeError, ValueError):
                print(f"[/trip] WARNING: w_risk_score not numeric: {w_risk_score!r}, defaulting to 0")
                w_risk_score = 0.0
            if int(weather_info.get("risk_level") or 0) >= 4 or w_risk_score >= 7:
                reasons.append(f"thời tiết nguy hiểm: {weather_info.get('message', '')}")
            elif w_risk_score >= 4:
                caution_reasons.append(weather_info.get("message") or "thời tiết không thuận lợi")
        else:
            caution_reasons.append("không lấy được đánh giá thời tiết")

        if reasons:
            recommendation = "❌ KHÔNG NÊN ĐI (" + ", ".join(reasons) + ")"
        elif caution_reasons:
            recommendation = "⚠️ CẨN THẬN (" + ", ".join(caution_reasons) + ")"

        # 6) Human-readable time
        tn = traffic.get("time_normal_min")
        tt = traffic.get("time_traffic_min")
        tnh = format_minutes_human(tn)
        tth = format_minutes_human(tt)

        result = {
            "assessed_at": datetime.now(timezone.utc).isoformat(),
            "departure_date": departure_date.isoformat() if departure_date else None,
            "current_weather": current_weather,
            "from": {"lat": lat_f, "lon": lon_f},
            "to": {
                "query": destination, "name": dest_name,
                "lat": float(dest_lat), "lon": float(dest_lon),
                "province_inferred": prov,
            },
            "traffic": {
                "status": traffic.get("status") or traffic.get("status_emoji"),
                "status_code": traffic.get("status"),
                "status_emoji": traffic.get("status_emoji"),
                "distance_km": traffic.get("distance_km"),
                "time_normal_min": tn,
                "time_traffic_min": tt,
                "time_normal": tnh,
                "time_traffic": tth,
                "time_normal_human": tnh,
                "time_traffic_human": tth,
                "speed_kmh": traffic.get("speed_kmh"),
                "traffic_score": traffic.get("traffic_score"),
                "delay_min": traffic.get("delay_min"),
                "traffic_available": traffic.get("traffic_available", False),
                "route_available": traffic.get("route_available", True),
                "traffic_source": traffic.get("traffic_source"),
                "message": traffic.get("message"),
                "route_polyline": traffic.get("route_polyline"),
                "route_polyline_provider": traffic.get("route_polyline_provider"),
                "route_polyline_type": traffic.get("route_polyline_type"),
            },
            "risk": {
                "risk_score": risk_score,
                "historical_risk_score": historical_risk_score,
                "historical_num_articles": historical_num_articles,
                "latest_article_date": latest_article_date,
                "data_status": risk_data_status,
                "recent_window_days": NEWS_RISK_MAX_AGE_DAYS,
                "num_articles": risk_num_articles,
                "model_scored_articles": model_scored_articles,
                "news_model_source": model_source,
                "risk_assessment": risk_assessment,
            },
            "weather": weather_info,
            "trip_purpose": trip_purpose,
            "recommendation": recommendation,
            "matched_province": matched_province,
        }

        # --- Sanitize numpy/pandas types for JSON serialization ---
        result = _sanitize_for_json(result)
        result["explanation"] = explain(result)

        # --- Save to trip history if logged in (never let a DB hiccup break /trip) ---
        if current_user:
            try:
                result["history_id"] = save_trip_history(current_user["id"], destination, lat_f, lon_f, trip_purpose, result)
            except Exception as e:
                print(f"[/trip] WARNING: failed to save trip history: {e}")

        # --- Save to cache ---
        if result["traffic"]["route_available"]:
            _trip_cache_set(cache_key, {k: v for k, v in result.items() if k != "history_id"})

        # Return via _safe_json_response to completely bypass FastAPI's jsonable_encoder
        return _safe_json_response(result)

    except HTTPException:
        # Re-raise FastAPI HTTP exceptions as-is (don't wrap them)
        raise
    except Exception as e:
        # ---- GLOBAL CATCH: log full traceback so the exact failing line is visible ----
        print(f"\n[/trip] UNHANDLED ERROR: {e!r}")
        print(traceback.format_exc())
        return JSONResponse(status_code=500, content={"error": "Internal Server Error in /trip"})


# ============================================================
# TRAFFIC ROUTE (address → address)
# ============================================================
@app.get("/debug/trip-cache")
def debug_trip_cache(clear: bool = False):
    """View or clear trip cache."""
    if clear:
        count = len(_trip_cache)
        _trip_cache.clear()
        return {"cleared": count}
    now = time.time()
    entries = []
    for k, v in _trip_cache.items():
        age = int(now - v["ts"])
        entries.append({"key": k, "age_sec": age, "ttl_remaining": max(0, _TRIP_CACHE_TTL - age)})
    return {"count": len(entries), "ttl_sec": _TRIP_CACHE_TTL, "entries": entries}


@app.get("/debug/weather-cache")
def debug_weather_cache(clear: bool = False):
    """View or clear weather + geocode + forecast caches."""
    if clear:
        wc = len(_weather_cache)
        gc = len(_geocode_cache)
        fc = len(_forecast_cache)
        _weather_cache.clear()
        _geocode_cache.clear()
        _forecast_cache.clear()
        return {"weather_cleared": wc, "geocode_cleared": gc, "forecast_cleared": fc}
    now = time.time()
    w_entries = []
    for k, v in _weather_cache.items():
        age = int(now - v["ts"])
        w_entries.append({"city": k, "age_sec": age, "ttl_remaining": max(0, _WEATHER_CACHE_TTL - age)})
    g_entries = []
    for k, v in _geocode_cache.items():
        age = int(now - v["ts"])
        g_entries.append({"city": k, "age_sec": age, "ttl_remaining": max(0, _GEOCODE_CACHE_TTL - age)})
    f_entries = []
    for k, v in _forecast_cache.items():
        age = int(now - v["ts"])
        f_entries.append({"key": k, "age_sec": age, "ttl_remaining": max(0, _FORECAST_CACHE_TTL - age)})
    return {
        "weather_cache": {"count": len(w_entries), "ttl_sec": _WEATHER_CACHE_TTL, "entries": w_entries},
        "geocode_cache": {"count": len(g_entries), "ttl_sec": _GEOCODE_CACHE_TTL, "entries": g_entries},
        "forecast_cache": {"count": len(f_entries), "ttl_sec": _FORECAST_CACHE_TTL, "entries": f_entries},
    }


@app.get("/debug/caches")
def debug_all_caches():
    """Overview of all caches in the system."""
    from src.api.utils import _df_cache
    return {
        "trip_cache": {
            "count": len(_trip_cache),
            "ttl_sec": _TRIP_CACHE_TTL,
            "max_size": 200,
        },
        "weather_cache": {
            "count": len(_weather_cache),
            "ttl_sec": _WEATHER_CACHE_TTL,
            "max_size": 100,
        },
        "forecast_cache": {
            "count": len(_forecast_cache),
            "ttl_sec": _FORECAST_CACHE_TTL,
            "max_size": 50,
        },
        "geocode_cache": {
            "count": len(_geocode_cache),
            "ttl_sec": _GEOCODE_CACHE_TTL,
            "max_size": 500,
        },
        "serpapi_geo_cache": {
            "count": len(_serpapi_geo_cache),
            "ttl_sec": _SERPAPI_GEO_CACHE_TTL,
            "max_size": 500,
        },
        "features_df": {
            "loaded": _df_cache is not None,
            "path": FEATURES_PATH,
        },
        "hint": "Use /debug/trip-cache?clear=true or /debug/weather-cache?clear=true to flush.",
    }


@app.get("/traffic/route")
def traffic_route(from_addr: str = Query(...), to_addr: str = Query(...)):
    lat1, lon1, name1 = search_location_google(from_addr)
    if lat1 is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy điểm đi: {from_addr}")

    lat2, lon2, name2 = search_location_google(to_addr)
    if lat2 is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy điểm đến: {to_addr}")

    try:
        traffic = check_route_traffic_google(name1, name2, lat1, lon1, lat2, lon2)
    except Exception as exc:
        print(f"[/traffic/route] Traffic provider unavailable: {type(exc).__name__}")
        traffic = unavailable_route()
    if not isinstance(traffic, dict) or not traffic or traffic.get("error"):
        traffic = unavailable_route()
    if traffic.get("route_available") is not False:
        ensure_route_polyline(traffic, float(lat1), float(lon1), float(lat2), float(lon2))

    tn, tt = traffic.get("time_normal_min"), traffic.get("time_traffic_min")
    return {
        "from": {"query": from_addr, "resolved": name1, "lat": float(lat1), "lon": float(lon1)},
        "to": {"query": to_addr, "resolved": name2, "lat": float(lat2), "lon": float(lon2)},
        "traffic": {
            **traffic,
            "time_normal": format_minutes_human(tn), "time_traffic": format_minutes_human(tt),
            "time_normal_human": format_minutes_human(tn), "time_traffic_human": format_minutes_human(tt),
        },
    }


# ============================================================
# MAP
# ============================================================
@app.get("/map/heat")
def map_heat():
    df = load_features_df(force=False)
    dfq = df[df["quality_pass"] == True].copy()
    agg = dfq.groupby("province", dropna=True).agg(
        num_articles=("id", "count"), avg_rule=("risk_score_effective", "mean")
    ).reset_index()
    agg["risk_score"] = (agg["avg_rule"] / 20.0 * 10.0).clip(0, 10)

    centroid = load_province_centroids()
    points, seen = [], set()
    for _, r in agg.iterrows():
        prov = (r["province"] or "").strip()
        if not prov:
            continue
        seen.add(prov)
        if prov not in centroid:
            continue
        lat, lon = centroid[prov]
        risk = float(r["risk_score"])
        points.append({"name": prov, "lat": lat, "lon": lon, "risk_score": int(round(risk)),
                        "num_articles": int(r["num_articles"]), "intensity": risk / 10.0})

    return {"points": points, "missing_provinces": sorted(p for p in seen if p not in centroid)}


@app.get("/map/points")
def map_points():
    cfg = load_provinces_yaml()
    points = []
    for p in cfg.get("provinces", []):
        name, lat, lon = p.get("name"), p.get("lat"), p.get("lon")
        if name is None or lat is None or lon is None:
            continue
        try:
            points.append({"province": str(name), "lat": float(lat), "lon": float(lon)})
        except Exception:
            continue
    return {"points": points}


# ============================================================
# AUTH + TRIP HISTORY
# ============================================================
app.include_router(auth_router)
app.include_router(notification_router)
from src.api.news_refresh import news_router
app.include_router(news_router)
from src.api.watches import watch_router
app.include_router(watch_router)
from src.api.receipts import receipt_router
app.include_router(receipt_router)


@app.get("/api/trip-history")
def get_trip_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    rows = list_trip_history(current_user["id"], limit=limit, offset=offset)
    return {"count": len(rows), "results": rows}


@app.delete("/api/trip-history/{trip_id}")
def remove_trip_history(trip_id: int, current_user: dict = Depends(get_current_user)):
    ok = delete_trip_history(trip_id, current_user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Trip not found")
    return {"deleted": True}


# ============================================================
# WEATHER AI — routed to weather_ai.py (Open-Meteo, free, no key)
# ============================================================
app.include_router(weather_router)
