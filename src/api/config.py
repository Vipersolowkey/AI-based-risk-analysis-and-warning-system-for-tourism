# src/api/config.py
"""
Centralized paths, constants, and province alias map.
"""
import os
import sys

# ============================================================
# PATHS
# ============================================================
THIS_FILE = os.path.abspath(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Load .env before reading any os.getenv() below, so every module that
# imports from config.py gets .env values without loading dotenv itself.
from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

FEATURES_PATH = os.path.join(PROJECT_ROOT, "data", "features", "articles_features.jsonl")
NEWS_PREDICTIONS_PATH = (os.getenv("NEWS_PREDICTIONS_PATH") or "").strip()
PHOBERT_PREDICTIONS_PATH = os.path.join(PROJECT_ROOT, "data", "outputs", "predictions.jsonl")
BASELINE_PREDICTIONS_PATH = os.path.join(PROJECT_ROOT, "data", "outputs", "news_baseline_predictions.jsonl")
PROVINCES_CFG = os.path.join(PROJECT_ROOT, "configs", "provinces.yaml")
WEATHER_MODEL_PATH = os.path.join(
    PROJECT_ROOT, "src", "integrations", "weather", "weather_risk_v5_classifier.pkl"
)
WEATHER_MODEL_FEATURES_PATH = os.path.join(
    PROJECT_ROOT, "src", "integrations", "weather", "model_features.json"
)

# ============================================================
# TRACKASIA
# ============================================================
TRACKASIA_KEY = (os.getenv("TRACKASIA_KEY") or "").strip()
TRACKASIA_BASE = (os.getenv("TRACKASIA_BASE") or "https://maps.track-asia.com").rstrip("/")

# ============================================================
# AUTH / JWT
# ============================================================
JWT_SECRET_DEFAULT = "travel-risk-local-development-secret-change-in-env"
JWT_SECRET = (os.getenv("JWT_SECRET") or JWT_SECRET_DEFAULT).strip()
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES") or "1440")

# ============================================================
# SQLITE (users / trip history / push subscriptions)
# ============================================================
# DB_PATH_OVERRIDE lets tests point at a throwaway sqlite file instead of
# the real app database.
DB_PATH = (os.getenv("DB_PATH_OVERRIDE") or os.path.join(PROJECT_ROOT, "data", "state", "app.sqlite"))

# ============================================================
# AIR QUALITY (OpenWeatherMap)
# ============================================================
OPENWEATHERMAP_API_KEY = (os.getenv("OPENWEATHERMAP_API_KEY") or "").strip()

# ============================================================
# WEB PUSH (VAPID)
# ============================================================
VAPID_PUBLIC_KEY = (os.getenv("VAPID_PUBLIC_KEY") or "").strip()
VAPID_PRIVATE_KEY = (os.getenv("VAPID_PRIVATE_KEY") or "").strip()
VAPID_CONTACT_EMAIL = (os.getenv("VAPID_CONTACT_EMAIL") or "mailto:admin@example.com").strip()

# ============================================================
# RISK CONFIG
# ============================================================
RISK_GROUPS = [
    "Pricing_Issue",
    "Environmental_Cleanliness",
    "Safety_Security",
    "Natural_Disaster",
    "Fire_Accident_Risk",
]
NEWS_RISK_MAX_AGE_DAYS = int(os.getenv("NEWS_RISK_MAX_AGE_DAYS") or "30")

# ============================================================
# PLACE ALIASES  (input key -> canonical Vietnamese name)
# ============================================================
PLACE_MAP = {
    # 5 Cities
    "TPHCM": "TP Hồ Chí Minh",
    "HCM": "TP Hồ Chí Minh",
    "SAIGON": "TP Hồ Chí Minh",
    "HOCHIMINH": "TP Hồ Chí Minh",
    "HN": "Hà Nội",
    "HANOI": "Hà Nội",
    "THUDO": "Hà Nội",
    "DN": "Đà Nẵng",
    "DANANG": "Đà Nẵng",
    "HP": "Hải Phòng",
    "HAIPHONG": "Hải Phòng",
    "CT": "Cần Thơ",
    "CANTHO": "Cần Thơ",
    # Provinces
    "ANGIANG": "An Giang",
    "BARIAVUNGTAU": "Bà Rịa - Vũng Tàu",
    "BRVT": "Bà Rịa - Vũng Tàu",
    "BACGIANG": "Bắc Giang",
    "BACKAN": "Bắc Kạn",
    "BACLIEU": "Bạc Liêu",
    "BACNINH": "Bắc Ninh",
    "BENTRE": "Bến Tre",
    "BINHDINH": "Bình Định",
    "QUYNHON": "Bình Định",
    "BINHDUONG": "Bình Dương",
    "BINHPHUOC": "Bình Phước",
    "BINHTHUAN": "Bình Thuận",
    "PHANTHIET": "Bình Thuận",
    "MUINE": "Bình Thuận",
    "CAMAU": "Cà Mau",
    "CAOBANG": "Cao Bằng",
    "DAKLAK": "Đắk Lắk",
    "BUONMATHUOT": "Đắk Lắk",
    "DAKNONG": "Đắk Nông",
    "DIENBIEN": "Điện Biên",
    "DIENBIENPHU": "Điện Biên",
    "DONGNAI": "Đồng Nai",
    "BIENHOA": "Đồng Nai",
    "DONGTHAP": "Đồng Tháp",
    "GIALAI": "Gia Lai",
    "PLEIKU": "Gia Lai",
    "HAGIANG": "Hà Giang",
    "HANAM": "Hà Nam",
    "HATINH": "Hà Tĩnh",
    "HAIDUONG": "Hải Dương",
    "HAUGIANG": "Hậu Giang",
    "HOABINH": "Hòa Bình",
    "HUNGYEN": "Hưng Yên",
    "KHANHHOA": "Khánh Hòa",
    "NHATRANG": "Khánh Hòa",
    "CAMRANH": "Khánh Hòa",
    "KIENGIANG": "Kiên Giang",
    "PHUQUOC": "Kiên Giang",
    "KONTUM": "Kon Tum",
    "LAICHAU": "Lai Châu",
    "LAMDONG": "Lâm Đồng",
    "DALAT": "Lâm Đồng",
    "LANGSON": "Lạng Sơn",
    "LAOCAI": "Lào Cai",
    "SAPA": "Lào Cai",
    "LONGAN": "Long An",
    "NAMDINH": "Nam Định",
    "NGHEAN": "Nghệ An",
    "VINH": "Nghệ An",
    "NINHBINH": "Ninh Bình",
    "TRANGAN": "Ninh Bình",
    "TAMCOC": "Ninh Bình",
    "NINHTHUAN": "Ninh Thuận",
    "PHANRANG": "Ninh Thuận",
    "PHUTHO": "Phú Thọ",
    "PHUYEN": "Phú Yên",
    "TUYHOA": "Phú Yên",
    "QUANGBINH": "Quảng Bình",
    "PHONGNHA": "Quảng Bình",
    "QUANGNAM": "Quảng Nam",
    "HOIAN": "Quảng Nam",
    "QUANGNGAI": "Quảng Ngãi",
    "LYSON": "Quảng Ngãi",
    "QUANGNINH": "Quảng Ninh",
    "HALONG": "Quảng Ninh",
    "QUANGTRI": "Quảng Trị",
    "SOCTRANG": "Sóc Trăng",
    "SONLA": "Sơn La",
    "MOCCHAU": "Sơn La",
    "TAYNINH": "Tây Ninh",
    "NUIBADEN": "Tây Ninh",
    "THAIBINH": "Thái Bình",
    "THAINGUYEN": "Thái Nguyên",
    "THANHHOA": "Thanh Hóa",
    "SAMSON": "Thanh Hóa",
    "THUATHIENHUE": "Thừa Thiên Huế",
    "HUE": "Thừa Thiên Huế",
    "TIENGIANG": "Tiền Giang",
    "MYTHO": "Tiền Giang",
    "TRAVINH": "Trà Vinh",
    "TUYENQUANG": "Tuyên Quang",
    "VINHLONG": "Vĩnh Long",
    "VINHPHUC": "Vĩnh Phúc",
    "TAMDAO": "Vĩnh Phúc",
    "YENBAI": "Yên Bái",
    "MUCANGCHAI": "Yên Bái",
}
