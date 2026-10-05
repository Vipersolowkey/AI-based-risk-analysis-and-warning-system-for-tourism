from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel
import pandas as pd
from typing import Optional, Dict, List
from datetime import datetime, timezone, timedelta
import time
import unicodedata
import re
from src.integrations.weather.main import HybridSafetyPredictor, WeatherPreprocessor, map_risk_level_v17, normalize_weather_score, derive_weather_features
from src.api.config import OPENWEATHERMAP_API_KEY
import requests

weather_router = APIRouter()
weather_model_system = None

# ===================== CACHES =====================
_WEATHER_CACHE_TTL = 600  # 10 minutes — weather doesn't change that fast
_weather_cache: Dict[str, dict] = {}  # key -> {"ts": float, "response": dict}

_GEOCODE_CACHE_TTL = 86400  # 24 hours — city coords don't change
_geocode_cache: Dict[str, dict] = {}  # key -> {"ts": float, "result": dict}

_FORECAST_CACHE_TTL = 1800  # 30 minutes — forecast data changes slowly
_forecast_cache: Dict[str, dict] = {}  # key -> {"ts": float, "response": dict}


def _weather_cache_key(city: str) -> str:
    return city.strip().lower()


def _weather_cache_get(key: str) -> Optional[dict]:
    entry = _weather_cache.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > _WEATHER_CACHE_TTL:
        _weather_cache.pop(key, None)
        return None
    return entry["response"]


def _weather_cache_set(key: str, response: dict):
    if len(_weather_cache) > 100:
        cutoff = time.time() - _WEATHER_CACHE_TTL
        expired = [k for k, v in _weather_cache.items() if v["ts"] < cutoff]
        for k in expired:
            _weather_cache.pop(k, None)
    _weather_cache[key] = {"ts": time.time(), "response": response}


def _geocode_cache_get(city: str) -> Optional[dict]:
    key = city.strip().lower()
    entry = _geocode_cache.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > _GEOCODE_CACHE_TTL:
        _geocode_cache.pop(key, None)
        return None
    return entry["result"]


def _geocode_cache_set(city: str, result: dict):
    key = city.strip().lower()
    if len(_geocode_cache) > 500:
        cutoff = time.time() - _GEOCODE_CACHE_TTL
        expired = [k for k, v in _geocode_cache.items() if v["ts"] < cutoff]
        for k in expired:
            _geocode_cache.pop(k, None)
    _geocode_cache[key] = {"ts": time.time(), "result": result}


def _forecast_cache_key(city: str, days: int) -> str:
    return f"{city.strip().lower()}|{days}"


def _forecast_cache_get(key: str) -> Optional[dict]:
    entry = _forecast_cache.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > _FORECAST_CACHE_TTL:
        _forecast_cache.pop(key, None)
        return None
    return entry["response"]


def _forecast_cache_set(key: str, response: dict):
    if len(_forecast_cache) > 50:
        cutoff = time.time() - _FORECAST_CACHE_TTL
        expired = [k for k, v in _forecast_cache.items() if v["ts"] < cutoff]
        for k in expired:
            _forecast_cache.pop(k, None)
    _forecast_cache[key] = {"ts": time.time(), "response": response}


# ===================== AIR QUALITY (OpenWeatherMap) =====================
_AIR_QUALITY_CACHE_TTL = 1800  # 30 minutes
_air_quality_cache: Dict[str, dict] = {}  # key -> {"ts": float, "pm25": float}
_PM25_FALLBACK = 10.0  # used when no API key configured or the call fails


def _air_quality_cache_key(lat: float, lon: float) -> str:
    # Round to ~1km precision so nearby requests share a cache entry.
    return f"{round(lat, 2)},{round(lon, 2)}"


def _fetch_air_quality(lat: Optional[float], lon: Optional[float]) -> float:
    """Get PM2.5 from OpenWeatherMap, then Open-Meteo Air Quality as fallback."""
    if lat is None or lon is None:
        return _PM25_FALLBACK

    key = _air_quality_cache_key(lat, lon)
    entry = _air_quality_cache.get(key)
    if entry and time.time() - entry["ts"] <= _AIR_QUALITY_CACHE_TTL:
        return entry["pm25"]

    pm25 = None
    if OPENWEATHERMAP_API_KEY:
        try:
            resp = requests.get(
                "https://api.openweathermap.org/data/2.5/air_pollution",
                params={"lat": lat, "lon": lon, "appid": OPENWEATHERMAP_API_KEY},
                timeout=5,
            )
            resp.raise_for_status()
            pm25 = float(resp.json()["list"][0]["components"]["pm2_5"])
        except Exception as e:
            print(f"[air_quality] OpenWeatherMap unavailable: {e}")

    if pm25 is None:
        try:
            resp = requests.get(
                "https://air-quality-api.open-meteo.com/v1/air-quality",
                params={"latitude": lat, "longitude": lon, "current": "pm2_5"},
                timeout=5,
            )
            resp.raise_for_status()
            pm25 = float(resp.json()["current"]["pm2_5"])
        except Exception as e:
            print(f"[air_quality] Open-Meteo unavailable; using fallback PM2.5: {e}")
            return _PM25_FALLBACK

    if not 0 <= pm25 < 10000:
        return _PM25_FALLBACK

    if len(_air_quality_cache) > 500:
        cutoff = time.time() - _AIR_QUALITY_CACHE_TTL
        expired = [k for k, v in _air_quality_cache.items() if v["ts"] < cutoff]
        for k in expired:
            _air_quality_cache.pop(k, None)
    _air_quality_cache[key] = {"ts": time.time(), "pm25": pm25}
    return pm25


# ===================== WEATHER AI PAYLOADS =====================
class WeatherAIPayload(BaseModel):
    province: str = "Unknown"
    temperature: float
    humidity: float
    precipitation: float
    wind: float
    pm25: float
    visibility_km: float
    uv_index: float
    location_encoded: int = 0
    elevation: float = 0.0
    has_disaster_history: int = 0
    slippery_index: float = 0.0
    visibility_block: float = 0.0
    smog_impact: float = 0.0
    vehicle_type: int = 0
    hour_of_day: int = 12

class WeatherAILivePayload(BaseModel):
    city: str
    province: Optional[str] = None
    trip_purpose: Optional[str] = None

class WeatherAIBatchPayload(BaseModel):
    """Batch weather AI prediction for multiple cities."""
    cities: List[str]

class WeatherAIForecastPayload(BaseModel):
    """Forecast weather AI prediction for a city (7 days)."""
    city: str
    province: Optional[str] = None
    days: int = 7  # 1-16

# ===================== OPEN-METEO INTEGRATION (FREE, NO KEY) =====================

# ===================== NORMALIZATION HELPERS =====================

# Vietnamese prefix patterns to strip from address parts
_VN_PREFIXES = re.compile(
    r"^(tp\.\s*|tp\s+|thành phố\s+|tỉnh\s+|huyện\s+|xã\s+|phường\s+|quận\s+|thị xã\s+|thị trấn\s+|thanh pho\s+|tinh\s+|huyen\s+|xa\s+|phuong\s+|quan\s+|thi xa\s+|thi tran\s+)",
    re.IGNORECASE,
)

def _remove_accents(text: str) -> str:
    """Remove Vietnamese diacritics/accents, keeping đ→d, Đ→D."""
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalize(text: str) -> str:
    """Normalize a Vietnamese string: NFC, lowercase, strip."""
    return unicodedata.normalize("NFC", text).strip().lower()


def _normalize_no_accent(text: str) -> str:
    """Normalize + remove accents for accent-insensitive matching."""
    return _remove_accents(_normalize(text))


def _strip_prefix(text: str) -> str:
    """Strip Vietnamese administrative prefixes (Tp., Thành phố, Tỉnh, etc.)."""
    return _VN_PREFIXES.sub("", text).strip()


# ===================== LOCATION ENCODING MAP (must match training data) =====================
LOCATION_ENCODING_MAP = {
    "Vinh Long": 60,
    "Bắc Kạn": 3,
    "An Giang": 0,
    "Thái Bình": 52,
    "Đà Nẵng": 14,
    "Trà Vinh": 58,
    "Bạc Liêu": 4,
    "Cao Bằng": 13,
    "Hòa Bình": 28,
    "Gia Lai": 20,
    "Bình Phước": 9,
    "Cà Mau": 11,
    "TP. Hồ Chí Minh": 57,
    "Cần Thơ": 12,
    "Hải Phòng": 26,
    "Đồng Nai": 18,
    "Bến Tre": 6,
    "Hải Dương": 25,
    "Ninh Bình": 40,
    "Lạng Sơn": 35,
    "Bình Dương": 8,
    "Điện Biên": 17,
    "Bắc Ninh": 5,
    "Thái Nguyên": 53,
    "Long An": 37,
    "Quảng Bình": 44,
    "Quảng Trị": 48,
    "Nghệ An": 39,
    "Hà Nội": 23,
    "Quảng Ngãi": 46,
    "Kiên Giang": 31,
    "Phú Yên": 43,
    "Hà Tĩnh": 24,
    "Tiền Giang": 56,
    "Sơn La": 50,
    "Bình Định": 7,
    "Đắk Lắk": 15,
    "Nam Định": 38,
    "Quảng Ninh": 47,
    "Hà Giang": 21,
    "Hưng Yên": 29,
    "Lai Châu": 33,
    "Lào Cai": 36,
    "Tây Ninh": 51,
    "Yên Bái": 62,
    "Bình Thuận": 10,
    "Tuyên Quang": 59,
    "Hậu Giang": 27,
    "Thanh Hóa": 54,
    "Lâm Đồng": 34,
    "Khánh Hòa": 30,
    "Quảng Nam": 45,
    "Kon Tum": 32,
    "Thừa Thiên Huế": 55,
    "Bắc Giang": 2,
    "Đắk Nông": 16,
    "Hà Nam": 22,
    "Vĩnh Phúc": 61,
    "Đồng Tháp": 19,
    "Ninh Thuận": 41,
    "Phú Thọ": 42,
    "Sóc Trăng": 49,
    "Bà Rịa - Vũng Tàu": 1,
}

# ===================== SPECIAL ALIASES =====================
# Maps common abbreviations / alternate names → canonical LOCATION_ENCODING_MAP key
_SPECIAL_ALIASES: Dict[str, str] = {
    # Ho Chi Minh City
    "tp. hồ chí minh": "TP. Hồ Chí Minh",
    "tp hồ chí minh": "TP. Hồ Chí Minh",
    "tphcm": "TP. Hồ Chí Minh",
    "sài gòn": "TP. Hồ Chí Minh",
    "saigon": "TP. Hồ Chí Minh",
    "sai gon": "TP. Hồ Chí Minh",
    "ho chi minh": "TP. Hồ Chí Minh",
    "hồ chí minh": "TP. Hồ Chí Minh",
    "thành phố hồ chí minh": "TP. Hồ Chí Minh",
    "thanh pho ho chi minh": "TP. Hồ Chí Minh",
    # Bà Rịa - Vũng Tàu
    "bà rịa - vũng tàu": "Bà Rịa - Vũng Tàu",
    "bà rịa vũng tàu": "Bà Rịa - Vũng Tàu",
    "ba ria - vung tau": "Bà Rịa - Vũng Tàu",
    "ba ria vung tau": "Bà Rịa - Vũng Tàu",
    "vũng tàu": "Bà Rịa - Vũng Tàu",
    "vung tau": "Bà Rịa - Vũng Tàu",
    # Thừa Thiên Huế
    "thừa thiên huế": "Thừa Thiên Huế",
    "thua thien hue": "Thừa Thiên Huế",
    "huế": "Thừa Thiên Huế",
    "hue": "Thừa Thiên Huế",
    # Đà Lạt → Lâm Đồng
    "đà lạt": "Lâm Đồng",
    "da lat": "Lâm Đồng",
    "dalat": "Lâm Đồng",
    # Nha Trang → Khánh Hòa
    "nha trang": "Khánh Hòa",
    # Hội An → Quảng Nam
    "hội an": "Quảng Nam",
    "hoi an": "Quảng Nam",
    # Quy Nhơn → Bình Định
    "quy nhơn": "Bình Định",
    "quy nhon": "Bình Định",
    # Phan Thiết → Bình Thuận
    "phan thiết": "Bình Thuận",
    "phan thiet": "Bình Thuận",
    # Phú Quốc → Kiên Giang
    "phú quốc": "Kiên Giang",
    "phu quoc": "Kiên Giang",
    # Sa Pa → Lào Cai
    "sa pa": "Lào Cai",
    "sapa": "Lào Cai",
    # Hà Nội
    "hà nội": "Hà Nội",
    "ha noi": "Hà Nội",
    "hanoi": "Hà Nội",
    # Đà Nẵng
    "đà nẵng": "Đà Nẵng",
    "da nang": "Đà Nẵng",
    "danang": "Đà Nẵng",
    # Hải Phòng
    "hải phòng": "Hải Phòng",
    "hai phong": "Hải Phòng",
    "haiphong": "Hải Phòng",
    # Cần Thơ
    "cần thơ": "Cần Thơ",
    "can tho": "Cần Thơ",
    # Cao Bằng
    "cao bằng": "Cao Bằng",
    "cao bang": "Cao Bằng",
    # Vinh → Nghệ An
    "vinh": "Nghệ An",
    # Buôn Ma Thuột → Đắk Lắk
    "buôn ma thuột": "Đắk Lắk",
    "buon ma thuot": "Đắk Lắk",
    # Pleiku → Gia Lai
    "pleiku": "Gia Lai",
    # Mỹ Tho → Tiền Giang
    "mỹ tho": "Tiền Giang",
    "my tho": "Tiền Giang",
    # Rạch Giá → Kiên Giang
    "rạch giá": "Kiên Giang",
    "rach gia": "Kiên Giang",
    # Cà Mau
    "cà mau": "Cà Mau",
    "ca mau": "Cà Mau",
    # Bạc Liêu
    "bạc liêu": "Bạc Liêu",
    "bac lieu": "Bạc Liêu",
    # Tam Kỳ → Quảng Nam
    "tam kỳ": "Quảng Nam",
    "tam ky": "Quảng Nam",
}

# Pre-build lookup tables for fast matching
# 1. accented lowercase → (canonical_name, code)
_LOC_ACCENTED: Dict[str, tuple] = {}
# 2. non-accented lowercase → (canonical_name, code)
_LOC_NO_ACCENT: Dict[str, tuple] = {}

def _build_location_lookups():
    """Build the fast-lookup dictionaries from LOCATION_ENCODING_MAP + _SPECIAL_ALIASES."""
    _LOC_ACCENTED.clear()
    _LOC_NO_ACCENT.clear()
    for name, code in LOCATION_ENCODING_MAP.items():
        nfc = _normalize(name)
        nfa = _normalize_no_accent(name)
        _LOC_ACCENTED[nfc] = (name, code)
        _LOC_NO_ACCENT[nfa] = (name, code)
    # Add special aliases (these resolve to canonical keys)
    for alias, canonical in _SPECIAL_ALIASES.items():
        code = LOCATION_ENCODING_MAP.get(canonical)
        if code is None:
            continue
        nfc = _normalize(alias)
        nfa = _normalize_no_accent(alias)
        if nfc not in _LOC_ACCENTED:
            _LOC_ACCENTED[nfc] = (canonical, code)
        if nfa not in _LOC_NO_ACCENT:
            _LOC_NO_ACCENT[nfa] = (canonical, code)

_build_location_lookups()

# Sorted keys by length descending for longest-match-first substring search
_LOC_ACCENTED_KEYS_SORTED = sorted(_LOC_ACCENTED.keys(), key=len, reverse=True)
_LOC_NO_ACCENT_KEYS_SORTED = sorted(_LOC_NO_ACCENT.keys(), key=len, reverse=True)


def _lookup_location_encoded(province: str) -> int:
    """Bulletproof Vietnamese province/city → location_encoded integer.

    Strategy (in order):
      1. Exact match (NFC-normalized, case-insensitive) against LOCATION_ENCODING_MAP
      2. Exact match against _SPECIAL_ALIASES
      3. Non-accented exact match (handles 'Da Lat' → 'Lâm Đồng')
      4. Strip Vietnamese prefixes (Tp., Thành phố, Tỉnh, …) and retry 1-3
      5. Substring search: for each known province name (longest first),
         check if it appears inside the input string (accented then non-accented)
      6. If input contains commas, split and try each part recursively
      7. Safety net: return 0 (An Giang default) — never throw

    Returns location_encoded int (0 if no match).
    """
    if not province or not province.strip():
        return 0

    text = _normalize(province)

    # --- Pass 1: exact accented match ---
    if text in _LOC_ACCENTED:
        return _LOC_ACCENTED[text][1]

    # --- Pass 2: exact non-accented match ---
    text_na = _normalize_no_accent(province)
    if text_na in _LOC_NO_ACCENT:
        return _LOC_NO_ACCENT[text_na][1]

    # --- Pass 3: strip prefix and retry ---
    stripped = _normalize(_strip_prefix(province))
    if stripped != text:
        if stripped in _LOC_ACCENTED:
            return _LOC_ACCENTED[stripped][1]
        stripped_na = _remove_accents(stripped)
        if stripped_na in _LOC_NO_ACCENT:
            return _LOC_NO_ACCENT[stripped_na][1]

    # --- Pass 4: longest substring match (accented) ---
    for key in _LOC_ACCENTED_KEYS_SORTED:
        if key in text:
            return _LOC_ACCENTED[key][1]

    # --- Pass 5: longest substring match (non-accented) ---
    for key in _LOC_NO_ACCENT_KEYS_SORTED:
        if key in text_na:
            return _LOC_NO_ACCENT[key][1]

    # --- Pass 6: comma-separated parts (recurse on each, pick longest match) ---
    if "," in province:
        parts = [p.strip() for p in province.split(",") if p.strip()]
        best_code = 0
        best_key_len = 0
        for part in parts:
            # Try the raw part
            code = _lookup_single_part(part)
            if code != 0:
                plen = len(_normalize(part))
                if plen > best_key_len:
                    best_code = code
                    best_key_len = plen
            # Also try with prefix stripped
            sp = _strip_prefix(part)
            if sp != part:
                code2 = _lookup_single_part(sp)
                if code2 != 0:
                    plen2 = len(_normalize(sp))
                    if plen2 > best_key_len:
                        best_code = code2
                        best_key_len = plen2
        if best_code != 0:
            return best_code

    # --- Safety net ---
    return 0


def _lookup_single_part(text: str) -> int:
    """Try to match a single address fragment (no comma splitting)."""
    if not text or not text.strip():
        return 0
    nfc = _normalize(text)
    if nfc in _LOC_ACCENTED:
        return _LOC_ACCENTED[nfc][1]
    nfa = _normalize_no_accent(text)
    if nfa in _LOC_NO_ACCENT:
        return _LOC_NO_ACCENT[nfa][1]
    # Substring (longest first)
    for key in _LOC_ACCENTED_KEYS_SORTED:
        if key in nfc:
            return _LOC_ACCENTED[key][1]
    for key in _LOC_NO_ACCENT_KEYS_SORTED:
        if key in nfa:
            return _LOC_NO_ACCENT[key][1]
    return 0


# Common Vietnamese city name variants for geocoding fallback
_CITY_ALIASES = {
    "da lat": ["Đà Lạt", "Dalat"],
    "dalat": ["Đà Lạt", "Da Lat"],
    "da nang": ["Đà Nẵng", "Danang"],
    "danang": ["Đà Nẵng", "Da Nang"],
    "ho chi minh": ["Hồ Chí Minh", "Saigon", "TPHCM"],
    "saigon": ["Hồ Chí Minh", "Ho Chi Minh"],
    "ha noi": ["Hà Nội", "Hanoi"],
    "hanoi": ["Hà Nội", "Ha Noi"],
    "hue": ["Huế", "Thua Thien Hue"],
    "nha trang": ["Nha Trang", "Khanh Hoa"],
    "cao bang": ["Cao Bằng"],
    "hai phong": ["Hải Phòng", "Haiphong"],
    "can tho": ["Cần Thơ"],
    "quy nhon": ["Quy Nhơn", "Binh Dinh"],
    "phan thiet": ["Phan Thiết", "Binh Thuan"],
    "vung tau": ["Vũng Tàu", "Ba Ria Vung Tau"],
    "sapa": ["Sa Pa", "Lào Cai"],
    "phu quoc": ["Phú Quốc", "Kien Giang"],
    "hoi an": ["Hội An", "Quang Nam"],
}


def _geocode_openmeteo(city_name: str) -> dict:
    """Use Open-Meteo Geocoding API to resolve city name -> lat/lon.
    Falls back to Vietnamese aliases if initial search fails.
    Also tries extracting known province/city names from long address strings."""
    cached_result = _geocode_cache_get(city_name)
    if cached_result:
        return cached_result

    url = "https://geocoding-api.open-meteo.com/v1/search"

    # ---- Build candidate list using normalization helpers ----
    candidates = [city_name]

    # Add city alias variants
    key = _normalize(city_name)
    key_na = _normalize_no_accent(city_name)
    if key in _CITY_ALIASES:
        candidates.extend(_CITY_ALIASES[key])
    if key_na in _CITY_ALIASES:
        candidates.extend(_CITY_ALIASES[key_na])

    # Try special alias → canonical province name
    if key in {_normalize(a) for a in _SPECIAL_ALIASES}:
        for alias, canonical in _SPECIAL_ALIASES.items():
            if _normalize(alias) == key:
                if canonical not in candidates:
                    candidates.append(canonical)
    if key_na in {_normalize_no_accent(a) for a in _SPECIAL_ALIASES}:
        for alias, canonical in _SPECIAL_ALIASES.items():
            if _normalize_no_accent(alias) == key_na:
                if canonical not in candidates:
                    candidates.append(canonical)

    # If the input looks like a long address (contains commas), extract parts
    if "," in city_name:
        parts = [p.strip() for p in city_name.split(",") if p.strip()]
        for part in parts:
            cleaned = _strip_prefix(part)
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)
            if part not in candidates:
                candidates.append(part)

    # Try matching known LOCATION_ENCODING_MAP keys as substrings of the input
    input_nfc = _normalize(city_name)
    input_na = _normalize_no_accent(city_name)
    for prov_name in LOCATION_ENCODING_MAP:
        prov_nfc = _normalize(prov_name)
        prov_na = _normalize_no_accent(prov_name)
        if prov_nfc in input_nfc or prov_na in input_na:
            if prov_name not in candidates:
                candidates.append(prov_name)

    # Try known city alias keys too
    for alias_key, alias_vals in _CITY_ALIASES.items():
        if alias_key in input_nfc or alias_key in input_na:
            for av in alias_vals:
                if av not in candidates:
                    candidates.append(av)

    for name in candidates:
        params = {"name": name, "count": 5, "language": "vi", "format": "json"}
        try:
            resp = requests.get(url, params=params, timeout=15)
        except Exception:
            continue
        if resp.status_code != 200:
            continue
        data = resp.json()
        results = data.get("results")
        if results:
            vn = [r for r in results if (r.get("country_code") or "").upper() == "VN"]
            if vn:
                _geocode_cache_set(city_name, vn[0])
                return vn[0]

    raise HTTPException(status_code=404, detail=f"Không xác định được tọa độ tại Việt Nam cho '{city_name}'")


def _get_with_retry(url: str, params: dict, timeout: int, attempts: int = 3):
    """GET with a couple of retries — some hosts (e.g. Railway's shared egress
    IPs) see intermittent slow/failed connections to external APIs that a
    retry clears up. Raises the last exception if all attempts fail."""
    last_exc = None
    for i in range(attempts):
        try:
            return requests.get(url, params=params, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last_exc = e
            if i < attempts - 1:
                time.sleep(0.5 * (i + 1))
    raise last_exc


def _fetch_openmeteo_weather(lat: float, lon: float) -> dict:
    """
    Fetch current + hourly weather from Open-Meteo Forecast API.
    Returns raw JSON response (includes utc_offset_seconds for timezone-aware hour).
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": "true",
        "hourly": "relativehumidity_2m,precipitation,uv_index,visibility",
        "timezone": "auto",  # Use "auto" so Open-Meteo returns utc_offset_seconds for the location
        "forecast_days": 1,
    }
    try:
        resp = _get_with_retry(url, params, timeout=20)
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Open-Meteo Forecast unreachable: {e}")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Open-Meteo Forecast error: {resp.text}")
    return resp.json()


def _fetch_openmeteo_forecast(lat: float, lon: float, days: int = 7) -> dict:
    """
    Fetch daily forecast from Open-Meteo for multi-day AI prediction.
    Returns raw JSON with daily arrays (includes utc_offset_seconds).
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max,uv_index_max",
        "hourly": "relativehumidity_2m,visibility",
        "timezone": "auto",  # Use "auto" so Open-Meteo returns utc_offset_seconds for the location
        "forecast_days": min(max(days, 1), 16),
    }
    try:
        resp = _get_with_retry(url, params, timeout=20)
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Open-Meteo Forecast unreachable: {e}")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Open-Meteo Forecast error: {resp.text}")
    return resp.json()


def _get_destination_local_hour(om_data: dict) -> int:
    """Calculate the exact local hour at the destination using Open-Meteo's
    utc_offset_seconds field.  Falls back to UTC+7 (Vietnam) if unavailable."""
    try:
        utc_offset = om_data.get("utc_offset_seconds")
        if utc_offset is not None:
            dest_tz = timezone(timedelta(seconds=int(utc_offset)))
        else:
            dest_tz = timezone(timedelta(hours=7))  # default Vietnam
        return datetime.now(dest_tz).hour
    except Exception:
        return datetime.now(timezone(timedelta(hours=7))).hour


def _sanitize_uv(uv_raw: float, hour_of_day: int) -> float:
    """Sanitize UV index based on local hour:
    - Night (18:00–05:59): UV must be 0
    - Day: cap at 15.0 only for extreme outliers / sensor errors.
      Real tropical Vietnam UV values (7–12) pass through unchanged
      so the 7-day forecast shows natural daily variation."""
    if hour_of_day >= 18 or hour_of_day < 6:
        return 0.0
    return min(max(uv_raw, 0.0), 15.0)


def _generate_health_advice(*, uv_index: float, temperature: float, precipitation: float, wind: float = 0.0, purpose: str = "standard") -> str:
    """Generate a friendly health/travel advisory string based on weather conditions and trip purpose."""
    purpose_key = (purpose or "standard").strip().lower()

    # Base health advice (weather-driven)
    base_advice = ""
    if uv_index > 7:
        base_advice = "Tia UV rất cao, hãy mang theo kem chống nắng và áo khoác! 🧴"
    elif temperature > 35:
        base_advice = "Trời rất nóng, nhớ uống đủ nước để tránh sốc nhiệt. 💧"
    elif precipitation > 5:
        base_advice = "Khả năng mưa lớn, đừng quên mang theo ô hoặc áo mưa nhé. ☔"
    else:
        base_advice = "Thời tiết khá lý tưởng cho các hoạt động ngoài trời. ✨"

    # Purpose-specific additions
    is_perfect = (uv_index <= 7 and temperature <= 35 and precipitation <= 5 and wind <= 20)
    is_rainy_windy = (precipitation > 5 or wind > 20)
    is_high_uv_or_risk = (uv_index > 7)

    if purpose_key == "dating":
        if is_perfect:
            base_advice += " Một tối hẹn hò lãng mạn đang chờ bạn đó! ❤️"
    elif purpose_key == "family":
        if is_high_uv_or_risk or precipitation > 5 or wind > 20:
            base_advice += " An toàn là trên hết, nhớ chuẩn bị kỹ cho cả nhà nhé! 👨‍👩‍👧‍👦"
    elif purpose_key == "adventure":
        if is_rainy_windy:
            base_advice += " Thời tiết đầy thử thách, đúng chất dân phượt luôn! 🏍️"
    elif purpose_key == "solo":
        base_advice += " Tận hưởng khoảng thời gian của riêng bạn nhé! 🎒"

    return base_advice


def _get_current_hour_index(hourly_time: list) -> int:
    """Find the index in hourly arrays closest to current Vietnam time (UTC+7).

    Open-Meteo returns naive local timestamps (Asia/Ho_Chi_Minh) when
    timezone is set.  We attach UTC+7 to each timestamp and compare
    against the real current time so both date *and* hour are matched
    correctly – the old code only compared hours and could pick the
    wrong slot around midnight."""
    _VN_TZ = timezone(timedelta(hours=7))
    now_vn = datetime.now(_VN_TZ)
    best_idx = 0
    best_diff = float("inf")
    for i, t_str in enumerate(hourly_time):
        try:
            t = datetime.fromisoformat(t_str)
            if t.tzinfo is None:
                t = t.replace(tzinfo=_VN_TZ)
            diff = abs((now_vn - t).total_seconds())
            if diff < best_diff:
                best_diff = diff
                best_idx = i
        except Exception:
            continue
    return best_idx


def transform_openmeteo_to_ai_format(om_data: dict, province: str = "Unknown", geo: dict = None, purpose: str = "standard") -> dict:
    """Transform Open-Meteo response into AI model input format.
    
    Produces all features required by model_features.json:
    location_encoded, temperature, humidity, precipitation, wind, pm25,
    visibility_km, uv_index, elevation, has_disaster_history,
    slippery_index, visibility_block, smog_impact, vehicle_type, hour_of_day
    """
    cw = om_data.get("current_weather", {})
    hourly = om_data.get("hourly", {})
    hourly_time = hourly.get("time", [])

    idx = _get_current_hour_index(hourly_time)

    def _safe_get(arr, i, default=0.0):
        if arr and 0 <= i < len(arr) and arr[i] is not None:
            return float(arr[i])
        return default

    humidity = _safe_get(hourly.get("relativehumidity_2m"), idx, 50.0)
    precipitation = _safe_get(hourly.get("precipitation"), idx, 0.0)
    uv_index_raw = _safe_get(hourly.get("uv_index"), idx, 5.0)
    visibility_m = _safe_get(hourly.get("visibility"), idx, 10000.0)
    visibility_km = visibility_m / 1000.0
    # The weather feed has no PM2.5; get it from an air-quality provider.
    pm25 = _fetch_air_quality(geo.get("latitude") if geo else None, geo.get("longitude") if geo else None)
    wind = float(cw.get("windspeed", 0.0))
    temperature = float(cw.get("temperature", 25.0))

    # ---- Timezone-aware hour of day from destination ----
    hour_of_day = _get_destination_local_hour(om_data)

    # ---- UV sanitization ----
    uv_index = _sanitize_uv(uv_index_raw, hour_of_day)

    # ---- Derived features for v4 model ----
    location_encoded = _lookup_location_encoded(province)  # Use helper function for encoding
    elevation = float(geo.get("elevation", 0.0)) if geo else float(om_data.get("elevation", 0.0))
    has_disaster_history = 0  # Default — no disaster history data available
    # Slippery index: higher when wet + humid
    slippery_index = round(min(precipitation / 50.0, 1.0) * (humidity / 100.0), 4)
    # Visibility block: inverse of visibility (1 = fully blocked, 0 = clear)
    visibility_block = round(max(1.0 - visibility_km / 10.0, 0.0), 4)
    # Smog impact: based on PM2.5 level (normalized)
    smog_impact = round(min(pm25 / 150.0, 1.0), 4)
    vehicle_type = 0  # Default: general / unknown vehicle type    # ---- Health advice ----
    health_advice = _generate_health_advice(
        uv_index=uv_index, temperature=temperature, precipitation=precipitation,
        wind=wind, purpose=purpose,
    )

    return {
        "location_encoded": location_encoded,
        "province": province,
        "temperature": temperature,
        "humidity": humidity,
        "precipitation": precipitation,
        "wind": wind,
        "pm25": pm25,
        "visibility_km": visibility_km,
        "uv_index": round(uv_index, 1),
        "elevation": elevation,
        "has_disaster_history": has_disaster_history,
        "slippery_index": slippery_index,
        "visibility_block": visibility_block,
        "smog_impact": smog_impact,
        "vehicle_type": vehicle_type,
        "hour_of_day": hour_of_day,
        "health_advice": health_advice,
    }


def _transform_daily_to_ai_inputs(forecast_data: dict, province: str = "Unknown", geo: dict = None, purpose: str = "standard") -> list:
    """Transform Open-Meteo daily forecast into list of AI model inputs (one per day)."""
    daily = forecast_data.get("daily", {})
    hourly = forecast_data.get("hourly", {})

    dates = daily.get("time", [])
    temp_max = daily.get("temperature_2m_max", [])
    temp_min = daily.get("temperature_2m_min", [])
    precip = daily.get("precipitation_sum", [])
    wind_max = daily.get("windspeed_10m_max", [])
    uv_max = daily.get("uv_index_max", [])

    # For humidity and visibility, average over each day's 24h block
    humidity_hourly = hourly.get("relativehumidity_2m", [])
    visibility_hourly = hourly.get("visibility", [])

    # Shared derived features
    location_encoded = _lookup_location_encoded(province)  # Use helper function for encoding
    elevation = float(geo.get("elevation", 0.0)) if geo else float(forecast_data.get("elevation", 0.0))
    has_disaster_history = 0
    # Same location for the whole forecast window — fetch PM2.5 once, not per day.
    pm25 = _fetch_air_quality(geo.get("latitude") if geo else None, geo.get("longitude") if geo else None)

    results = []
    for i, d in enumerate(dates):
        # Average temperature for the day
        t_max = temp_max[i] if i < len(temp_max) and temp_max[i] is not None else 30.0
        t_min = temp_min[i] if i < len(temp_min) and temp_min[i] is not None else 22.0
        temp_avg = (t_max + t_min) / 2.0

        p = precip[i] if i < len(precip) and precip[i] is not None else 0.0
        w = wind_max[i] if i < len(wind_max) and wind_max[i] is not None else 0.0
        uv = uv_max[i] if i < len(uv_max) and uv_max[i] is not None else 5.0

        # Daily avg humidity/visibility from hourly (24h per day)
        h_start, h_end = i * 24, (i + 1) * 24
        hum_slice = humidity_hourly[h_start:h_end]
        vis_slice = visibility_hourly[h_start:h_end]
        hum_vals = [v for v in hum_slice if v is not None]
        vis_vals = [v for v in vis_slice if v is not None]
        humidity = sum(hum_vals) / len(hum_vals) if hum_vals else 60.0
        visibility_m = sum(vis_vals) / len(vis_vals) if vis_vals else 10000.0
        visibility_km = visibility_m / 1000.0

        # Derived features for v4 model
        slippery_index = round(min(p / 50.0, 1.0) * (humidity / 100.0), 4)
        visibility_block = round(max(1.0 - visibility_km / 10.0, 0.0), 4)
        smog_impact = round(min(pm25 / 150.0, 1.0), 4)
        vehicle_type = 0
        # For daily forecasts use midday (12) as representative hour
        hour_of_day = 12

        # UV sanitization: daily uv_max is a daytime metric, but cap for model stability
        uv_sanitized = _sanitize_uv(uv, hour_of_day)        # Health advice per day
        health_advice = _generate_health_advice(
            uv_index=uv_sanitized, temperature=temp_avg, precipitation=p,
            wind=w, purpose=purpose,
        )

        results.append({
            "date": d,
            "input": {
                "location_encoded": location_encoded,
                "province": province,
                "temperature": round(temp_avg, 1),
                "humidity": round(humidity, 1),
                "precipitation": round(p, 1),
                "wind": round(w, 1),
                "pm25": pm25,
                "visibility_km": round(visibility_km, 2),
                "uv_index": round(uv_sanitized, 1),
                "elevation": elevation,
                "has_disaster_history": has_disaster_history,
                "slippery_index": slippery_index,
                "visibility_block": visibility_block,
                "smog_impact": smog_impact,
                "vehicle_type": vehicle_type,
                "hour_of_day": hour_of_day,
            },
            "detail": {
                "temp_max": round(t_max, 1),
                "temp_min": round(t_min, 1),
                "health_advice": health_advice,
            },
        })
    return results


# ===================== MSG MAP =====================
MSG_MAP = {
    0: "An toàn - Trời đẹp.",
    1: "Rủi ro thấp - Có thể có mưa nhỏ.",
    2: "Trung bình - Đường trơn, giảm tốc độ.",
    3: "Cao - Mưa lớn hoặc gió mạnh. Nguy hiểm.",
    4: "Rất cao - Cân nhắc hủy chuyến đi.",
    5: "THẢM HỌA - TUYỆT ĐỐI KHÔNG DI CHUYỂN!",
}

# ===================== TRIP PURPOSE RISK ADJUSTMENT =====================
# Each purpose defines:
#   base_modifier  — flat additive shift to risk_score
#   rain_sensitivity — extra penalty per mm of precipitation (above threshold)
#   wind_sensitivity — extra penalty per km/h of wind (above threshold)
#   uv_sensitivity   — extra penalty per UV unit (above threshold)
#   min_score / max_score — clamp adjusted score
#   label — Vietnamese display name
TRIP_PURPOSE_CONFIG = {
    "standard": {
        "label": "Tiêu chuẩn",
        "base_modifier": 0.0,
        "rain_threshold": 10.0,
        "rain_sensitivity": 0.15,
        "wind_threshold": 25,
        "wind_sensitivity": 0.05,
        "uv_threshold": 10,
        "uv_sensitivity": 0.08,
        "visibility_threshold": 2.0,
        "visibility_penalty": 0.2,
        "min_score": 1.0,
        "max_score": 10.0,
    },
    "dating": {
        "label": "Hẹn hò",
        "base_modifier": 0.8,
        "rain_threshold": 1.0,
        "rain_sensitivity": 0.35,
        "wind_threshold": 15,
        "wind_sensitivity": 0.10,
        "uv_threshold": 8,
        "uv_sensitivity": 0.15,
        "visibility_threshold": 5.0,
        "visibility_penalty": 0.3,
        "min_score": 1.0,
        "max_score": 10.0,
    },
    "family": {
        "label": "Gia đình",
        "base_modifier": 1.2,
        "rain_threshold": 2.0,
        "rain_sensitivity": 0.40,
        "wind_threshold": 12,
        "wind_sensitivity": 0.15,
        "uv_threshold": 7,
        "uv_sensitivity": 0.20,
        "visibility_threshold": 4.0,
        "visibility_penalty": 0.5,
        "min_score": 1.0,
        "max_score": 10.0,
    },
    "adventure": {
        "label": "Phiêu lưu",
        "base_modifier": -0.5,
        "rain_threshold": 15.0,
        "rain_sensitivity": 0.15,
        "wind_threshold": 30,
        "wind_sensitivity": 0.05,
        "uv_threshold": 10,
        "uv_sensitivity": 0.08,
        "visibility_threshold": 2.0,
        "visibility_penalty": 0.4,
        "min_score": 1.0,
        "max_score": 10.0,
    },
    "solo": {
        "label": "Một mình",
        "base_modifier": 0.0,
        "rain_threshold": 5.0,
        "rain_sensitivity": 0.20,
        "wind_threshold": 20,
        "wind_sensitivity": 0.08,
        "uv_threshold": 9,
        "uv_sensitivity": 0.10,
        "visibility_threshold": 3.0,
        "visibility_penalty": 0.3,
        "min_score": 1.0,
        "max_score": 10.0,
    },
}


def adjust_risk_for_purpose(
    base_score: float,
    purpose: str,
    weather_data: Optional[dict] = None,
) -> dict:
    """Adjust a base risk score based on trip purpose and weather conditions.

    Parameters
    ----------
    base_score : float
        The raw ML-predicted risk score (0-10).
    purpose : str
        One of "standard", "dating", "family", "adventure", "solo" (case-insensitive).
    weather_data : dict, optional
        Dict with keys like temperature, humidity, precipitation, wind,
        uv_index, visibility_km.  If None, only base purpose modifier is applied.

    Returns
    -------
    dict with keys:
        adjusted_score (float), adjusted_reason (str), purpose_label (str)
    """
    import traceback as _tb

    try:
        # ---- Type safety: ensure base_score is a float ----
        try:
            base_score = float(base_score)
        except (TypeError, ValueError) as e:
            print(f"[adjust_risk_for_purpose] Cannot convert base_score={base_score!r} to float: {e}")
            return {
                "adjusted_score": 5.0,
                "adjusted_reason": "Lỗi: không thể chuyển đổi điểm gốc",
                "purpose_label": "",
            }

        purpose_key = (purpose or "standard").strip().lower()
        cfg = TRIP_PURPOSE_CONFIG.get(purpose_key)
        if cfg is None:
            print(f"[adjust_risk_for_purpose] Unknown purpose '{purpose_key}', falling back to 'standard'")
            purpose_key = "standard"
            cfg = TRIP_PURPOSE_CONFIG["standard"]

        label = cfg["label"]
        reasons: list[str] = []

        # ---- Extract weather values safely ----
        precip = 0.0
        wind = 0.0
        temp = 25.0
        uv = 0.0
        vis = 10.0
        if weather_data:
            precip = float(weather_data.get("precipitation", 0) or 0)
            wind = float(weather_data.get("wind", 0) or 0)
            temp = float(weather_data.get("temperature", 25) or 25)
            uv = float(weather_data.get("uv_index", 0) or 0)
            vis = float(weather_data.get("visibility_km", 10) or 10)

        # ---- Purpose-specific adjustment logic (clean if-elif) ----
        adjusted = base_score

        if purpose_key == "family":
            # Safety margin for families with children/elderly
            adjusted *= 1.2
            reasons.append(f"Chuyến gia đình: biên an toàn x1.2 ({base_score:.2f} → {adjusted:.2f})")

        elif purpose_key == "dating":
            if precip > 2:
                adjusted += 1.0
                reasons.append(f"Hẹn hò + mưa {precip:.1f}mm → +1.0")
            elif 20 < temp < 26:
                adjusted -= 0.5
                reasons.append(f"Hẹn hò + thời tiết dễ chịu {temp:.1f}°C → −0.5")

        elif purpose_key == "adventure":
            if wind > 20:
                adjusted -= 1.0
                reasons.append(f"Phiêu lưu chấp nhận gió mạnh {wind:.0f}km/h → −1.0")

        elif purpose_key == "solo":
            # Solo: apply config-based modifier (neutral by default)
            adjusted += float(cfg["base_modifier"])
            if cfg["base_modifier"] != 0:
                reasons.append(f"Chuyến một mình: điều chỉnh {cfg['base_modifier']:+.1f}")

        else:
            # "standard" or any other — apply config-based modifier
            adjusted += float(cfg["base_modifier"])
            if cfg["base_modifier"] != 0:
                reasons.append(f"Điều chỉnh cơ bản: {cfg['base_modifier']:+.1f}")

        # ---- Additional weather penalties from config (all purposes) ----
        if weather_data:
            if precip > cfg["rain_threshold"]:
                extra = (precip - cfg["rain_threshold"]) * cfg["rain_sensitivity"]
                adjusted += extra
                reasons.append(f"Mưa {precip:.1f}mm vượt ngưỡng (+{extra:.1f})")

            if wind > cfg["wind_threshold"]:
                extra = (wind - cfg["wind_threshold"]) * cfg["wind_sensitivity"]
                adjusted += extra
                reasons.append(f"Gió {wind:.0f}km/h vượt ngưỡng (+{extra:.1f})")

            if uv > cfg["uv_threshold"]:
                extra = (uv - cfg["uv_threshold"]) * cfg["uv_sensitivity"]
                adjusted += extra
                reasons.append(f"UV {uv:.1f} cao (+{extra:.1f})")

            if vis < cfg["visibility_threshold"]:
                adjusted += cfg["visibility_penalty"]
                reasons.append(f"Tầm nhìn thấp {vis:.1f}km (+{cfg['visibility_penalty']})")

        # ---- Strict bounds: clamp to [1.0, 10.0] ----
        final_score = round(min(max(adjusted, 1.0), 10.0), 2)
        # Trip preferences must not reduce a severe model/safety result.
        if base_score >= 7.0:
            final_score = max(final_score, round(min(base_score, 10.0), 2))

        # ---- Purpose-specific motivational/advisory suffix ----
        is_perfect = (precip <= 2 and wind <= 15 and uv <= 7 and temp >= 20 and temp <= 30)
        is_high_risk = (final_score >= 7 or uv > cfg["uv_threshold"])
        is_rainy_windy = (precip > 5 or wind > 20)

        purpose_suffix = ""
        if purpose_key == "dating" and is_perfect:
            purpose_suffix = "Một tối hẹn hò lãng mạn đang chờ bạn đó! ❤️"
        elif purpose_key == "family" and (is_high_risk or uv > cfg["uv_threshold"]):
            purpose_suffix = "An toàn là trên hết, nhớ chuẩn bị kỹ cho cả nhà nhé! 👨‍👩‍👧‍👦"
        elif purpose_key == "adventure" and is_rainy_windy:
            purpose_suffix = "Thời tiết đầy thử thách, đúng chất dân phượt luôn! 🏍️"
        elif purpose_key == "solo":
            purpose_suffix = "Tận hưởng khoảng thời gian của riêng bạn nhé! 🎒"

        reason_text = "; ".join(reasons) if reasons else f"Chuyến {label.lower()} — không có điều chỉnh đặc biệt"
        if purpose_suffix:
            reason_text = f"{reason_text}. {purpose_suffix}" if reasons else purpose_suffix

        return {
            "adjusted_score": final_score,
            "adjusted_reason": reason_text,
            "purpose_label": label,
        }

    except Exception as e:
        print(f"[adjust_risk_for_purpose] ERROR: purpose={purpose!r}, base_score={base_score!r}, err={e!r}")
        print(_tb.format_exc())
        # Fallback: return base score clamped to [1.0, 10.0] instead of crashing
        fallback = 5.0
        try:
            fallback = min(max(round(float(base_score), 2), 1.0), 10.0)
        except Exception:
            pass
        return {
            "adjusted_score": fallback,
            "adjusted_reason": f"Lỗi khi điều chỉnh: {e}",
            "purpose_label": "",
        }


# ===================== ENDPOINTS =====================

def register_weather_model(model):
    global weather_model_system
    weather_model_system = model


def weather_prediction_fields(score: float, level: int, method: str) -> dict:
    """Expose a consistent score scale in every weather API response."""
    return {
        "risk_level": int(level),
        "risk_score": round(normalize_weather_score(score), 2),
        "model_score_0_20": round(float(score), 2),
        "message": MSG_MAP.get(int(level), "Unknown"),
        "detection_method": method,
    }


def assess_weather_risk(lat: float, lon: float, province: str = "Unknown", purpose: str = "standard") -> Optional[dict]:
    """Shared weather-risk assessment for known coordinates — used by both
    /trip's fetch_weather() path and the Web Push check-now trigger, so the
    scoring logic (fetch -> transform -> predict) only lives in one place."""
    if not weather_model_system:
        return None
    cache_key = _weather_cache_key(f"{lat:.3f},{lon:.3f}")
    om_data = _weather_cache_get(cache_key)
    if not om_data:
        om_data = _fetch_openmeteo_weather(lat, lon)
        _weather_cache_set(cache_key, om_data)

    geo_info = {"elevation": om_data.get("elevation", 0.0), "latitude": lat, "longitude": lon}
    ai_input = transform_openmeteo_to_ai_format(om_data, province=province, geo=geo_info, purpose=purpose)
    df = pd.DataFrame([ai_input])
    score, level, method = weather_model_system.predict(df)
    return weather_prediction_fields(score, level, method)


@weather_router.post("/weather/ai")
def weather_ai_predict(data: WeatherAIPayload):
    """Predict weather risk from manual payload (offline)."""
    if not weather_model_system:
        raise HTTPException(status_code=500, detail="Weather AI model not loaded")
    input_dict = derive_weather_features(data.model_dump())
    # Resolve location_encoded from province name if not explicitly set
    if input_dict.get("location_encoded", 0) == 0 and input_dict.get("province", "Unknown") != "Unknown":
        input_dict["location_encoded"] = _lookup_location_encoded(input_dict["province"])
    df = pd.DataFrame([input_dict])
    score, level, method = weather_model_system.predict(df)
    return weather_prediction_fields(score, level, method)


@weather_router.post("/weather/ai/live")
def weather_ai_live_predict(data: WeatherAILivePayload = Body(...)):
    """
    Fetches LIVE weather from Open-Meteo (free, no API key),
    transforms to AI format, and predicts risk.
    """
    if not weather_model_system:
        raise HTTPException(status_code=500, detail="Weather AI model not loaded")

    # 1. Geocode city name -> lat/lon
    geo = _geocode_openmeteo(data.city)
    lat = geo["latitude"]
    lon = geo["longitude"]
    resolved_name = geo.get("name", data.city)

    # 2. Fetch weather
    cache_key = _weather_cache_key(data.city)
    cached_weather = _weather_cache_get(cache_key)
    if cached_weather:
        om_data = cached_weather
    else:
        om_data = _fetch_openmeteo_weather(lat, lon)
        _weather_cache_set(cache_key, om_data)    # 3. Transform to AI input
    province = data.province or resolved_name
    trip_purpose = (data.trip_purpose or "standard").strip().lower()
    ai_input = transform_openmeteo_to_ai_format(om_data, province=province, geo=geo, purpose=trip_purpose)

    # 4. Predict
    df = pd.DataFrame([ai_input])
    score, level, method = weather_model_system.predict(df)

    result = {
        "city_resolved": resolved_name,
        "coordinates": {"lat": lat, "lon": lon},
        "input": ai_input,
        **weather_prediction_fields(score, level, method),
        "health_advice": ai_input.get("health_advice", ""),
        "weather_provider": "Open-Meteo (free, no key)",
    }

    # 5. Trip purpose adjustment (if provided)
    if data.trip_purpose:
        try:
            adj = adjust_risk_for_purpose(normalize_weather_score(score), data.trip_purpose, weather_data=ai_input)
            result["trip_purpose"] = data.trip_purpose
            result["purpose_label"] = adj["purpose_label"]
            result["adjusted_risk_score"] = adj["adjusted_score"]
            result["adjusted_reason"] = adj["adjusted_reason"]
        except Exception as e:
            print(f"[/weather/ai/live] ERROR in adjust_risk_for_purpose: {e} | score={score}, purpose={data.trip_purpose}")
            result["trip_purpose"] = data.trip_purpose
            result["adjusted_risk_score"] = round(normalize_weather_score(score), 2)
            result["adjusted_reason"] = f"Lỗi điều chỉnh: {e}"

    return result


@weather_router.get("/weather/ai/forecast")
def weather_ai_forecast(
    city: str = Query(..., description="City name, e.g. 'Đà Nẵng'"),
    province: Optional[str] = Query(None),
    days: int = Query(7, ge=1, le=16, description="Number of forecast days (1-16)"),
    trip_purpose: Optional[str] = Query(None, description="Trip purpose: dating, family, adventure, solo"),
    lat: Optional[float] = Query(None, ge=-90, le=90, description="Resolved destination latitude"),
    lon: Optional[float] = Query(None, ge=-180, le=180, description="Resolved destination longitude"),
):
    """
    7-day (or custom) weather forecast with AI risk prediction per day.
    Uses Open-Meteo daily forecast → AI model prediction for each day.
    FREE, no API key needed.
    """
    if not weather_model_system:
        raise HTTPException(status_code=500, detail="Weather AI model not loaded")

    # A trip already has resolved destination coordinates. Re-geocoding its
    # display name can silently select another city (or the Hanoi fallback).
    if (lat is None) != (lon is None):
        raise HTTPException(status_code=422, detail="Provide both lat and lon")
    geo = (
        {"latitude": lat, "longitude": lon, "name": city}
        if lat is not None else _geocode_openmeteo(city)
    )
    lat, lon = geo["latitude"], geo["longitude"]
    resolved_name = geo.get("name", city)

    # 2. Fetch daily forecast (with cache)
    fc_key = _forecast_cache_key(f"{city}|{lat:.5f}|{lon:.5f}", days)
    cached_fc = _forecast_cache_get(fc_key)
    if cached_fc:
        forecast_data = cached_fc
    else:
        forecast_data = _fetch_openmeteo_forecast(lat, lon, days)
        _forecast_cache_set(fc_key, forecast_data)    # 3. Transform to AI inputs
    province_label = province or resolved_name
    purpose_key = (trip_purpose or "standard").strip().lower()
    daily_inputs = _transform_daily_to_ai_inputs(forecast_data, province=province_label, geo=geo, purpose=purpose_key)

    # 4. BATCH predict — build one DataFrame for all days, call predict once
    batch_rows = [day_item["input"] for day_item in daily_inputs]
    batch_df = pd.DataFrame(batch_rows)

    # Use predict_batch if available (single XGBoost call), fallback to loop
    if hasattr(weather_model_system, 'predict_batch'):
        batch_results = weather_model_system.predict_batch(batch_df)
    else:
        batch_results = [weather_model_system.predict(pd.DataFrame([row])) for row in batch_rows]

    daily_results = []
    for day_item, (score, level, method) in zip(daily_inputs, batch_results):
        day_result = {
            "date": day_item["date"],
            **weather_prediction_fields(score, level, method),
            "temperature": day_item["input"]["temperature"],
            "temp_max": day_item["detail"]["temp_max"],
            "temp_min": day_item["detail"]["temp_min"],
            "humidity": day_item["input"]["humidity"],
            "precipitation": day_item["input"]["precipitation"],
            "wind": day_item["input"]["wind"],
            "visibility_km": day_item["input"]["visibility_km"],
            "uv_index": day_item["input"]["uv_index"],
            "health_advice": day_item["detail"].get("health_advice", ""),
        }
        # Trip purpose adjustment per day
        if trip_purpose:
            try:
                adj = adjust_risk_for_purpose(normalize_weather_score(score), trip_purpose, weather_data=day_item["input"])
                day_result["adjusted_risk_score"] = adj["adjusted_score"]
                day_result["adjusted_reason"] = adj["adjusted_reason"]
                day_result["purpose_label"] = adj["purpose_label"]
            except Exception as e:
                print(f"[/weather/ai/forecast] ERROR in adjust_risk_for_purpose: {e} | score={score}, purpose={trip_purpose}")
                day_result["adjusted_risk_score"] = round(normalize_weather_score(score), 2)
                day_result["adjusted_reason"] = f"Lỗi điều chỉnh: {e}"
        daily_results.append(day_result)

    # Overall summary: worst day + best day
    worst = max(daily_results, key=lambda x: x["risk_score"]) if daily_results else None
    best = min(daily_results, key=lambda x: x["risk_score"]) if daily_results else None

    result = {
        "city_resolved": resolved_name,
        "coordinates": {"lat": lat, "lon": lon},
        "province": province_label,
        "forecast_days": len(daily_results),
        "daily": daily_results,
        "worst_day": worst,
        "best_day": best,
        "weather_provider": "Open-Meteo (free, no key)",
    }
    if trip_purpose:
        result["trip_purpose"] = trip_purpose
        purpose_cfg = TRIP_PURPOSE_CONFIG.get(trip_purpose.strip().lower())
        if purpose_cfg:
            result["purpose_label"] = purpose_cfg["label"]
    return result


@weather_router.post("/weather/ai/batch")
def weather_ai_batch(data: WeatherAIBatchPayload = Body(...)):
    """
    Batch weather AI prediction for multiple cities at once.
    Max 10 cities per request. Returns current weather risk for each.
    Uses batch prediction — single model.predict() call for all cities.
    """
    if not weather_model_system:
        raise HTTPException(status_code=500, detail="Weather AI model not loaded")

    cities = [c.strip() for c in data.cities if c.strip()]
    if not cities:
        raise HTTPException(status_code=422, detail="cities list is empty")
    if len(cities) > 10:
        raise HTTPException(status_code=422, detail="Max 10 cities per batch request")

    # Phase 1: Gather all weather data and AI inputs
    city_meta = []  # list of dicts with city info + ai_input (or error)
    for city in cities:
        try:
            geo = _geocode_openmeteo(city)
            lat, lon = geo["latitude"], geo["longitude"]
            resolved = geo.get("name", city)

            cache_key = _weather_cache_key(city)
            cached_w = _weather_cache_get(cache_key)
            if cached_w:
                om_data = cached_w
            else:
                om_data = _fetch_openmeteo_weather(lat, lon)
                _weather_cache_set(cache_key, om_data)

            ai_input = transform_openmeteo_to_ai_format(om_data, province=resolved, geo=geo)
            city_meta.append({"city": city, "resolved": resolved, "lat": lat, "lon": lon, "ai_input": ai_input, "error": None})
        except Exception as e:
            city_meta.append({"city": city, "error": str(e)})

    # Phase 2: Batch predict all valid inputs at once
    valid_indices = [i for i, m in enumerate(city_meta) if m.get("error") is None]
    if valid_indices:
        batch_rows = [city_meta[i]["ai_input"] for i in valid_indices]
        batch_df = pd.DataFrame(batch_rows)
        if hasattr(weather_model_system, 'predict_batch'):
            batch_preds = weather_model_system.predict_batch(batch_df)
        else:
            batch_preds = [weather_model_system.predict(pd.DataFrame([row])) for row in batch_rows]
        for idx, (score, level, method) in zip(valid_indices, batch_preds):
            city_meta[idx]["prediction"] = (score, level, method)

    # Phase 3: Build results
    results = []
    for m in city_meta:
        if m.get("error"):
            results.append({"city": m["city"], "error": m["error"]})
            continue
        score, level, method = m["prediction"]
        ai_input = m["ai_input"]
        results.append({
            "city": m["city"],
            "city_resolved": m["resolved"],
            "coordinates": {"lat": m["lat"], "lon": m["lon"]},
            **weather_prediction_fields(score, level, method),
            "temperature": ai_input.get("temperature"),
            "humidity": ai_input.get("humidity"),
            "precipitation": ai_input.get("precipitation"),
            "wind": ai_input.get("wind"),
            "visibility_km": ai_input.get("visibility_km"),
            "uv_index": ai_input.get("uv_index"),
            "health_advice": ai_input.get("health_advice", ""),
        })

    # Sort by risk_score descending (errors last)
    results.sort(key=lambda x: x.get("risk_score", -1), reverse=True)

    return {
        "count": len(results),
        "results": results,
        "weather_provider": "Open-Meteo (free, no key)",
    }
