# =======================================================
# FILE: main.py
# MỤC ĐÍCH: API SERVER CHO WEATHER MODEL V5
# =======================================================

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd
import numpy as np
import json
import os
import re
import unicodedata
from contextlib import asynccontextmanager
import joblib
from sklearn.base import BaseEstimator, TransformerMixin

# -------------------------------------------------------
# PHẦN 1: ĐỊNH NGHĨA CLASS (ĐỂ LOAD ĐƯỢC FILE .PKL)
# -------------------------------------------------------

class WeatherPreprocessor(BaseEstimator, TransformerMixin):
    def __init__(self):
        self.prov_cols = []
        self.feature_order = []
    
    def fit(self, X, y=None): return self
    
    def transform(self, X):
        df = X.copy()
        # Xử lý Dummy Province
        if 'province' in df.columns:
            dummies = pd.get_dummies(df['province'], prefix='prov')
            for col in self.prov_cols:
                df[col] = dummies[col] if col in dummies else 0
        else:
            for col in self.prov_cols: df[col] = 0
            
        weather_features = ["temperature", "humidity", "precipitation", 
                            "wind", "pm25", "visibility_km", "uv_index"]
        
        for col in weather_features:
            if col not in df.columns: df[col] = 0 
        
        final_cols = weather_features + self.prov_cols
        return df.reindex(columns=self.feature_order, fill_value=0)

def map_risk_level_v17(score):
    if score < 3: return 0
    elif score < 6: return 1
    elif score < 9: return 2
    elif score < 12: return 3
    elif score < 16: return 4
    return 5


def normalize_weather_score(raw_score):
    """Convert the model's 0–20 score to the 0–10 API/advice scale."""
    score = float(raw_score)
    if not np.isfinite(score):
        return 10.0
    return float(np.clip(score / 2.0, 0.0, 10.0))


# Representative 0–20 scores for the weather dataset's five trained classes.
# Level 5 is reserved for the hard safety gates.
CLASS_SCORE_0_20 = {0: 1.0, 1: 4.0, 2: 7.0, 3: 10.0, 4: 14.0}


def derive_weather_features(data: dict) -> dict:
    """Apply the same deterministic feature engineering used for training."""
    values = dict(data)
    precipitation = max(float(values.get("precipitation", 0) or 0), 0.0)
    humidity = float(np.clip(float(values.get("humidity", 0) or 0), 0.0, 100.0))
    visibility = max(float(values.get("visibility_km", 0) or 0), 0.0)
    pm25 = max(float(values.get("pm25", 0) or 0), 0.0)
    values["slippery_index"] = round(min(precipitation / 50.0, 1.0) * (humidity / 100.0), 4)
    values["visibility_block"] = round(max(1.0 - visibility / 10.0, 0.0), 4)
    values["smog_impact"] = round(min(pm25 / 150.0, 1.0), 4)
    return values

# Class Hybrid Wrapper (Chứa logic Safety Gate)
class HybridSafetyPredictor:
    def __init__(self, ml_pipeline, feature_names=None):
        self.pipeline = ml_pipeline
        self.feature_names = feature_names  # ordered list from model_features.json
    
    def _align_features(self, input_df):
        """Ensure the input DataFrame columns match model_features.json order.
        Missing columns are filled with 0; extra columns are dropped."""
        if not self.feature_names:
            return input_df
        for col in self.feature_names:
            if col not in input_df.columns:
                input_df[col] = 0
        return input_df[self.feature_names]
    
    def _check_safety_gate(self, row):
        """Check safety gate rules for a single row. Returns (score, level, method) or None."""
        if row.get('precipitation', 0) > 150 and row.get('wind', 0) > 80:
            return 20.0, 5, "SAFETY_GATE_STORM"
        if row.get('precipitation', 0) > 200:
            return 20.0, 5, "SAFETY_GATE_FLOOD"
        if row.get('precipitation', 0) > 120 and row.get('visibility_km', 10) < 1.0:
            return 18.0, 5, "SAFETY_GATE_DANGEROUS_VISIBILITY"
        return None

    def _interpret_prediction(self, prediction):
        if hasattr(self.pipeline, "predict_proba") and hasattr(self.pipeline, "classes_"):
            level = int(prediction)
            if level not in CLASS_SCORE_0_20:
                raise ValueError(f"Unexpected weather class: {level}")
            return CLASS_SCORE_0_20[level], level, "AI_XGBOOST"
        raw_score = float(prediction)
        if not np.isfinite(raw_score):
            return 20.0, 5, "FAILSAFE_NAN"
        return raw_score, map_risk_level_v17(raw_score), "AI_XGBOOST"

    def predict(self, input_df):
        row = input_df.iloc[0]
        # --- SAFETY GATES (Luật cứng) ---
        gate = self._check_safety_gate(row)
        if gate:
            return gate
        # --- AI PREDICTION ---
        try:
            aligned_df = self._align_features(input_df.copy())
            prediction = self.pipeline.predict(aligned_df)[0]
            return self._interpret_prediction(prediction)
        except Exception as e:
            print(f"[Weather AI] Prediction error: {e}")
            return 20.0, 5, "FAILSAFE_CRASH"

    def predict_batch(self, input_df):
        """Batch prediction: predict all rows at once. Returns list of (score, level, method).
        
        Safety gates are checked per-row first. Remaining rows are batched through
        the ML pipeline in a single predict() call for maximum throughput."""
        n = len(input_df)
        results = [None] * n
        ml_indices = []

        # 1) Check safety gates per row
        for i in range(n):
            row = input_df.iloc[i]
            gate = self._check_safety_gate(row)
            if gate:
                results[i] = gate
            else:
                ml_indices.append(i)

        # 2) Batch ML prediction for non-gated rows
        if ml_indices:
            try:
                batch_df = input_df.iloc[ml_indices].copy()
                aligned_df = self._align_features(batch_df)
                predictions = self.pipeline.predict(aligned_df)
                for idx, prediction in zip(ml_indices, predictions):
                    results[idx] = self._interpret_prediction(prediction)
            except Exception as e:
                print(f"[Weather AI] Batch prediction error: {e}")
                for idx in ml_indices:
                    if results[idx] is None:
                        results[idx] = (20.0, 5, "FAILSAFE_CRASH")

        return results

# -------------------------------------------------------
# PHẦN 2: KHỞI TẠO SERVER API
# -------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_model()
    yield


app = FastAPI(
    title="Weather Risk AI API",
    description="API đánh giá rủi ro thời tiết cho lộ trình đường đi",
    version="5.0",
    lifespan=lifespan,
)

# Biến toàn cục để chứa model
model_system = None

# Sự kiện chạy 1 lần duy nhất khi bật Server
def load_model():
    global model_system
    try:
        # Load file model .pkl
        print("⏳ Đang tải model V5...")
        model_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(model_dir, "weather_risk_v5_classifier.pkl")
        features_path = os.path.join(model_dir, "model_features.json")

        bundle = joblib.load(model_path)
        # If the pkl contains a dict (legacy), extract the pipeline; otherwise use directly
        if isinstance(bundle, dict):
            pipeline = bundle.get('pipeline', bundle.get('model', bundle))
        else:
            pipeline = bundle

        # Load feature names from model_features.json
        feature_names = None
        if os.path.exists(features_path):
            with open(features_path, "r", encoding="utf-8") as f:
                feature_names = json.load(f)
            print(f"✅ Loaded {len(feature_names)} feature names: {feature_names}")
        else:
            print(f"⚠️ {features_path} not found, using model defaults")
        
        # Tái tạo hệ thống Hybrid
        model_system = HybridSafetyPredictor(pipeline, feature_names=feature_names)
        print("✅ AI Model V5 Loaded Successfully! Sẵn sàng phục vụ.")
    except Exception as e:
        print(f"❌ LỖI NGHIÊM TRỌNG: Không thể load model. Chi tiết: {e}")

# -------------------------------------------------------
# PHẦN 3: ĐỊNH NGHĨA INPUT/OUTPUT VÀ ENDPOINT
# -------------------------------------------------------

# ===================== NORMALIZATION HELPERS =====================

_VN_PREFIXES = re.compile(
    r"^(tp\.\s*|tp\s+|thành phố\s+|tỉnh\s+|huyện\s+|xã\s+|phường\s+|quận\s+|thị xã\s+|thị trấn\s+|thanh pho\s+|tinh\s+|huyen\s+|xa\s+|phuong\s+|quan\s+|thi xa\s+|thi tran\s+)",
    re.IGNORECASE,
)

def _remove_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))

def _normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip().lower()

def _normalize_no_accent(text: str) -> str:
    return _remove_accents(_normalize(text))

def _strip_prefix(text: str) -> str:
    return _VN_PREFIXES.sub("", text).strip()


# ===================== LOCATION ENCODING MAP (must match training data) =====================
LOCATION_ENCODING_MAP = {
    "Vinh Long": 60, "Bắc Kạn": 3, "An Giang": 0, "Thái Bình": 52,
    "Đà Nẵng": 14, "Trà Vinh": 58, "Bạc Liêu": 4, "Cao Bằng": 13,
    "Hòa Bình": 28, "Gia Lai": 20, "Bình Phước": 9, "Cà Mau": 11,
    "TP. Hồ Chí Minh": 57, "Cần Thơ": 12, "Hải Phòng": 26, "Đồng Nai": 18,
    "Bến Tre": 6, "Hải Dương": 25, "Ninh Bình": 40, "Lạng Sơn": 35,
    "Bình Dương": 8, "Điện Biên": 17, "Bắc Ninh": 5, "Thái Nguyên": 53,
    "Long An": 37, "Quảng Bình": 44, "Quảng Trị": 48, "Nghệ An": 39,
    "Hà Nội": 23, "Quảng Ngãi": 46, "Kiên Giang": 31, "Phú Yên": 43,
    "Hà Tĩnh": 24, "Tiền Giang": 56, "Sơn La": 50, "Bình Định": 7,
    "Đắk Lắk": 15, "Nam Định": 38, "Quảng Ninh": 47, "Hà Giang": 21,
    "Hưng Yên": 29, "Lai Châu": 33, "Lào Cai": 36, "Tây Ninh": 51,
    "Yên Bái": 62, "Bình Thuận": 10, "Tuyên Quang": 59, "Hậu Giang": 27,
    "Thanh Hóa": 54, "Lâm Đồng": 34, "Khánh Hòa": 30, "Quảng Nam": 45,
    "Kon Tum": 32, "Thừa Thiên Huế": 55, "Bắc Giang": 2, "Đắk Nông": 16,
    "Hà Nam": 22, "Vĩnh Phúc": 61, "Đồng Tháp": 19, "Ninh Thuận": 41,
    "Phú Thọ": 42, "Sóc Trăng": 49, "Bà Rịa - Vũng Tàu": 1,
}

# ===================== SPECIAL ALIASES =====================
_SPECIAL_ALIASES = {
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
    "bà rịa - vũng tàu": "Bà Rịa - Vũng Tàu",
    "bà rịa vũng tàu": "Bà Rịa - Vũng Tàu",
    "ba ria - vung tau": "Bà Rịa - Vũng Tàu",
    "ba ria vung tau": "Bà Rịa - Vũng Tàu",
    "vũng tàu": "Bà Rịa - Vũng Tàu",
    "vung tau": "Bà Rịa - Vũng Tàu",
    "thừa thiên huế": "Thừa Thiên Huế",
    "thua thien hue": "Thừa Thiên Huế",
    "huế": "Thừa Thiên Huế",
    "hue": "Thừa Thiên Huế",
    "đà lạt": "Lâm Đồng",
    "da lat": "Lâm Đồng",
    "dalat": "Lâm Đồng",
    "nha trang": "Khánh Hòa",
    "hội an": "Quảng Nam",
    "hoi an": "Quảng Nam",
    "quy nhơn": "Bình Định",
    "quy nhon": "Bình Định",
    "phan thiết": "Bình Thuận",
    "phan thiet": "Bình Thuận",
    "phú quốc": "Kiên Giang",
    "phu quoc": "Kiên Giang",
    "sa pa": "Lào Cai",
    "sapa": "Lào Cai",
    "hà nội": "Hà Nội",
    "ha noi": "Hà Nội",
    "hanoi": "Hà Nội",
    "đà nẵng": "Đà Nẵng",
    "da nang": "Đà Nẵng",
    "danang": "Đà Nẵng",
    "hải phòng": "Hải Phòng",
    "hai phong": "Hải Phòng",
    "haiphong": "Hải Phòng",
    "cần thơ": "Cần Thơ",
    "can tho": "Cần Thơ",
    "cao bằng": "Cao Bằng",
    "cao bang": "Cao Bằng",
    "vinh": "Nghệ An",
    "buôn ma thuột": "Đắk Lắk",
    "buon ma thuot": "Đắk Lắk",
    "pleiku": "Gia Lai",
    "mỹ tho": "Tiền Giang",
    "my tho": "Tiền Giang",
    "rạch giá": "Kiên Giang",
    "rach gia": "Kiên Giang",
    "cà mau": "Cà Mau",
    "ca mau": "Cà Mau",
    "bạc liêu": "Bạc Liêu",
    "bac lieu": "Bạc Liêu",
    "tam kỳ": "Quảng Nam",
    "tam ky": "Quảng Nam",
}

# Pre-build lookup tables
_LOC_ACCENTED = {}
_LOC_NO_ACCENT = {}

def _build_location_lookups():
    _LOC_ACCENTED.clear()
    _LOC_NO_ACCENT.clear()
    for name, code in LOCATION_ENCODING_MAP.items():
        nfc = _normalize(name)
        nfa = _normalize_no_accent(name)
        _LOC_ACCENTED[nfc] = (name, code)
        _LOC_NO_ACCENT[nfa] = (name, code)
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

_LOC_ACCENTED_KEYS_SORTED = sorted(_LOC_ACCENTED.keys(), key=len, reverse=True)
_LOC_NO_ACCENT_KEYS_SORTED = sorted(_LOC_NO_ACCENT.keys(), key=len, reverse=True)


def _lookup_single_part(text: str) -> int:
    if not text or not text.strip():
        return 0
    nfc = _normalize(text)
    if nfc in _LOC_ACCENTED:
        return _LOC_ACCENTED[nfc][1]
    nfa = _normalize_no_accent(text)
    if nfa in _LOC_NO_ACCENT:
        return _LOC_NO_ACCENT[nfa][1]
    for key in _LOC_ACCENTED_KEYS_SORTED:
        if key in nfc:
            return _LOC_ACCENTED[key][1]
    for key in _LOC_NO_ACCENT_KEYS_SORTED:
        if key in nfa:
            return _LOC_NO_ACCENT[key][1]
    return 0


def _lookup_location_encoded(province: str) -> int:
    """Bulletproof Vietnamese province/city -> location_encoded integer.
    Never throws. Returns 0 if no match found."""
    if not province or not province.strip():
        return 0

    text = _normalize(province)

    # Pass 1: exact accented match
    if text in _LOC_ACCENTED:
        return _LOC_ACCENTED[text][1]

    # Pass 2: exact non-accented match
    text_na = _normalize_no_accent(province)
    if text_na in _LOC_NO_ACCENT:
        return _LOC_NO_ACCENT[text_na][1]

    # Pass 3: strip prefix and retry
    stripped = _normalize(_strip_prefix(province))
    if stripped != text:
        if stripped in _LOC_ACCENTED:
            return _LOC_ACCENTED[stripped][1]
        stripped_na = _remove_accents(stripped)
        if stripped_na in _LOC_NO_ACCENT:
            return _LOC_NO_ACCENT[stripped_na][1]

    # Pass 4: longest substring match (accented)
    for key in _LOC_ACCENTED_KEYS_SORTED:
        if key in text:
            return _LOC_ACCENTED[key][1]

    # Pass 5: longest substring match (non-accented)
    for key in _LOC_NO_ACCENT_KEYS_SORTED:
        if key in text_na:
            return _LOC_NO_ACCENT[key][1]

    # Pass 6: comma-separated parts
    if "," in province:
        parts = [p.strip() for p in province.split(",") if p.strip()]
        best_code = 0
        best_key_len = 0
        for part in parts:
            code = _lookup_single_part(part)
            if code != 0:
                plen = len(_normalize(part))
                if plen > best_key_len:
                    best_code = code
                    best_key_len = plen
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

    # Safety net
    return 0


# Định dạng dữ liệu đầu vào (Backend phải gửi đúng form này)
class WeatherPayload(BaseModel):
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

# Định nghĩa đường dẫn API (Endpoint)
@app.post("/predict")
async def predict_risk(data: WeatherPayload):
    # Kiểm tra model đã load chưa
    if not model_system:
        raise HTTPException(status_code=500, detail="Model chưa sẵn sàng")
    
    # 1. Chuyển JSON thành DataFrame
    input_dict = derive_weather_features(data.model_dump())
    # Resolve location_encoded from province name if not explicitly set
    if input_dict.get("location_encoded", 0) == 0 and input_dict.get("province", "Unknown") != "Unknown":
        input_dict["location_encoded"] = _lookup_location_encoded(input_dict["province"])
    df = pd.DataFrame([input_dict])
    
    # 2. Dự đoán
    score, level, method = model_system.predict(df)
    
    # 3. Tạo thông báo thân thiện cho Frontend
    msg_map = {
        0: "An toàn - Trời đẹp.",
        1: "Rủi ro thấp - Có thể có mưa nhỏ.",
        2: "Trung bình - Đường trơn, giảm tốc độ.",
        3: "Cao - Mưa lớn hoặc gió mạnh. Nguy hiểm.",
        4: "Rất cao - Cân nhắc hủy chuyến đi.",
        5: "THẢM HỌA - TUYỆT ĐỐI KHÔNG DI CHUYỂN!"
    }

    # 4. Trả kết quả JSON về cho Backend
    return {
        "risk_level": int(level),
        "risk_score": round(normalize_weather_score(score), 2),
        "model_score_0_20": round(float(score), 2),
        "message": msg_map.get(int(level), "Unknown"),
        "detection_method": method
    }

# Đoạn code để chạy server khi bấm Run
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
