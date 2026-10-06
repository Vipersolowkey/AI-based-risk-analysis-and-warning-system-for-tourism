# src/api/utils.py
"""
Shared helpers: text normalization, JSONL I/O, province YAML,
DataFrame schema, risk scoring, time formatting.
"""
import json
import os
import re
import unicodedata
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml
from fastapi import HTTPException

from src.api.config import (
    FEATURES_PATH, PROVINCES_CFG, RISK_GROUPS, PLACE_MAP,
    NEWS_PREDICTIONS_PATH, PHOBERT_PREDICTIONS_PATH, BASELINE_PREDICTIONS_PATH,
    NEWS_RISK_MAX_AGE_DAYS, PROJECT_ROOT,
)

# ============================================================
# In-memory DataFrame cache
# ============================================================
_df_cache: Optional[pd.DataFrame] = None
_df_mtime: Optional[tuple] = None

# ============================================================
# Province YAML cache (file rarely changes)
# ============================================================
_provinces_yaml_cache: Optional[Dict[str, Any]] = None
_provinces_yaml_mtime: Optional[float] = None
_province_centroids_cache: Optional[Dict[str, Tuple[float, float]]] = None
_province_alias_cache: Optional[Dict[str, str]] = None


# ---- Pre-compiled regex patterns ----
_RE_WHITESPACE = re.compile(r"\s+")

# ---- text helpers ----

def normalize_key(place: str) -> str:
    return (
        (place or "").strip().upper()
        .replace(" ", "").replace(".", "")
        .replace("-", "").replace("_", "")
    )


def strip_accents(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def norm_text(s: str) -> str:
    s = strip_accents((s or "").lower())
    return _RE_WHITESPACE.sub(" ", s).strip()


# ---- JSONL I/O ----

def safe_read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    bad_lines = 0
    first_bad = None

    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
                else:
                    bad_lines += 1
            except Exception as e:
                bad_lines += 1
                if first_bad is None:
                    first_bad = {"line_no": i, "error": str(e), "line_head": line[:200]}

    if bad_lines:
        print(f"[API WARN] skipped_bad_lines={bad_lines}")
        if first_bad:
            print(f"[API WARN] first_bad={first_bad}")
    return rows


# ---- DataFrame helpers ----

def _to_list_safe(x) -> List[Any]:
    return [v for v in x if isinstance(v, str)] if isinstance(x, list) else []


def _published_to_str(x) -> str:
    if isinstance(x, str):
        return x
    if x is None:
        return ""
    try:
        return json.dumps(x, ensure_ascii=False)
    except Exception:
        return str(x)


def _published_to_date(x):
    """Parse one RSS timestamp while keeping its original calendar date.

    RSS feeds mix timezone offsets. Parsing the whole Series at once fails on
    recent pandas versions, and forcing UTC can move a Vietnamese article to
    the previous day.
    """
    raw = _published_to_str(x)
    if not raw:
        return None
    timestamp = pd.to_datetime(raw, errors="coerce")
    return None if pd.isna(timestamp) else timestamp.date()


def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    defaults = {
        "province": None, "quality_pass": False, "published_at": None,
        "risk_groups": None, "risk_score_rule": 0.0, "id": None,
    }
    for col, default in defaults.items():
        if col not in df.columns:
            if col == "risk_groups":
                df[col] = [[] for _ in range(len(df))]
            else:
                df[col] = default

    df["quality_pass"] = df["quality_pass"].fillna(False).astype(bool)
    df["risk_groups"] = df["risk_groups"].apply(_to_list_safe)
    df["risk_score_rule"] = pd.to_numeric(df["risk_score_rule"], errors="coerce").fillna(0.0)

    df["pub_date"] = df["published_at"].apply(_published_to_date)
    return df


def _news_predictions_files() -> List[str]:
    """Apply baseline predictions, then override matching articles with PhoBERT."""
    override = NEWS_PREDICTIONS_PATH
    if override and not os.path.isabs(override):
        override = os.path.join(PROJECT_ROOT, override)
    paths = (BASELINE_PREDICTIONS_PATH, PHOBERT_PREDICTIONS_PATH, override)
    return list(dict.fromkeys(path for path in paths if path and os.path.exists(path)))


def _attach_news_predictions(df: pd.DataFrame, paths: List[str]) -> pd.DataFrame:
    existing = pd.to_numeric(df.get("p_risk_any"), errors="coerce") if "p_risk_any" in df else pd.Series(float("nan"), index=df.index)
    sources = pd.Series("rules", index=df.index)
    sources.loc[existing.notna()] = df.loc[existing.notna(), 'news_model_source'] if 'news_model_source' in df else "features_embedded"
    for path in paths:
        predictions = safe_read_jsonl(path)
        probability_by_id = {}
        source_by_id = {}
        for row in predictions:
            article_id = row.get("id")
            try:
                probability = float(row.get("p_risk_any"))
            except (TypeError, ValueError):
                continue
            if article_id and 0.0 <= probability <= 1.0:
                probability_by_id[article_id] = probability
                source_by_id[article_id] = row.get("model_source") or (
                    "phobert" if path == PHOBERT_PREDICTIONS_PATH else "tfidf_logreg"
                )
        if probability_by_id:
            from_file = df["id"].map(probability_by_id)
            matched = from_file.notna()
            existing.loc[matched] = from_file.loc[matched]
            sources.loc[matched] = df.loc[matched, "id"].map(source_by_id)
            print(f"[API] News model source={path}, scored={int(matched.sum())}/{len(df)}")
    df["p_risk_any"] = existing.clip(0.0, 1.0)
    df["news_model_source"] = sources
    # PhoBERT / baseline predicts whether an article is about risk. The rule
    # score still measures incident severity and identifies the risk category.
    df["risk_score_effective"] = df["risk_score_rule"] * df["p_risk_any"].fillna(1.0)
    return df


def load_features_df(force: bool = False) -> pd.DataFrame:
    global _df_cache, _df_mtime

    if not os.path.exists(FEATURES_PATH):
        raise HTTPException(status_code=404, detail=f"Missing features file: {FEATURES_PATH}")

    predictions_paths = _news_predictions_files()
    from src.api.news_refresh import news_revision, live_rows
    mtime = (os.path.getmtime(FEATURES_PATH),
             tuple((path, os.path.getmtime(path)) for path in predictions_paths), news_revision())
    if (not force) and (_df_cache is not None) and (_df_mtime == mtime):
        return _df_cache

    rows = safe_read_jsonl(FEATURES_PATH)
    rows.extend(live_rows())
    if not rows:
        raise HTTPException(status_code=400, detail="No valid JSON rows in features JSONL.")

    df = pd.DataFrame(rows)
    df = _attach_news_predictions(ensure_schema(df), predictions_paths)

    _df_cache = df
    _df_mtime = mtime
    print(f"[API] Loaded features rows={len(df)} from {FEATURES_PATH}")
    return df


# ---- Place resolution ----

def resolve_place(place: str) -> str:
    raw = (place or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="place is required")
    return PLACE_MAP.get(normalize_key(raw), raw)


# ---- Risk scoring ----

def score_from_subset(df_sub: pd.DataFrame) -> Dict[str, Any]:
    n = int(len(df_sub))
    counts = {g: 0 for g in RISK_GROUPS}
    probabilities = df_sub["p_risk_any"].tolist() if "p_risk_any" in df_sub else [None] * n
    for groups, probability in zip(df_sub["risk_groups"].tolist(), probabilities):
        if probability is not None and pd.notna(probability) and probability < 0.5:
            continue
        for g in groups:
            if g in counts:
                counts[g] += 1

    score_column = "risk_score_effective" if "risk_score_effective" in df_sub else "risk_score_rule"
    avg_rule = float(df_sub[score_column].mean()) if n > 0 else 0.0
    overall = max(0.0, min(10.0, (avg_rule / 20.0) * 10.0))

    model_scored = int(df_sub["p_risk_any"].notna().sum()) if "p_risk_any" in df_sub else 0
    source_names = sorted(df_sub["news_model_source"].dropna().unique()) if n and "news_model_source" in df_sub else ["rules"]
    model_source = "+".join(source_names)
    dates = df_sub["pub_date"].dropna() if n and "pub_date" in df_sub else []
    latest_date = max(dates) if len(dates) else None
    age_days = max(0, (date.today() - latest_date).days) if latest_date else None

    return {
        "num_articles": n,
        "model_scored_articles": model_scored,
        "news_model_source": model_source,
        "latest_article_date": latest_date.isoformat() if latest_date else None,
        "data_age_days": age_days,
        "is_stale": age_days is None or age_days > NEWS_RISK_MAX_AGE_DAYS,
        "risk_assessment": counts,
        "overall_risk_score": int(round(overall)),
    }


# ---- Province YAML helpers ----

def load_provinces_yaml() -> Dict[str, Any]:
    global _provinces_yaml_cache, _provinces_yaml_mtime, _province_centroids_cache, _province_alias_cache
    if not os.path.exists(PROVINCES_CFG):
        raise HTTPException(status_code=404, detail=f"Missing: {PROVINCES_CFG}")
    mtime = os.path.getmtime(PROVINCES_CFG)
    if _provinces_yaml_cache is not None and _provinces_yaml_mtime == mtime:
        return _provinces_yaml_cache
    with open(PROVINCES_CFG, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    _provinces_yaml_cache = data
    _provinces_yaml_mtime = mtime
    # Invalidate dependent caches
    _province_centroids_cache = None
    _province_alias_cache = None
    return data


def load_province_centroids() -> Dict[str, Tuple[float, float]]:
    global _province_centroids_cache, _provinces_yaml_mtime
    # Reuse yaml cache mtime check
    cfg = load_provinces_yaml()
    current_mtime = _provinces_yaml_mtime
    if _province_centroids_cache is not None:
        return _province_centroids_cache
    out: Dict[str, Tuple[float, float]] = {}
    for it in cfg.get("provinces", []):
        name = (it.get("name") or "").strip()
        lat, lon = it.get("lat"), it.get("lon")
        if name and isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            out[name] = (float(lat), float(lon))
    _province_centroids_cache = out
    return out


def build_alias_index(cfg: Dict[str, Any]) -> Dict[str, str]:
    idx: Dict[str, str] = {}
    for p in cfg.get("provinces", []):
        name = (p.get("name") or "").strip()
        if not name:
            continue
        idx[norm_text(name)] = name
        for a in (p.get("aliases") or []):
            na = norm_text(str(a))
            if na:
                idx[na] = name
    return idx


def infer_province_from_text(text: str) -> Optional[str]:
    global _province_alias_cache
    if not text:
        return None
    cfg = load_provinces_yaml()
    if _province_alias_cache is None:
        _province_alias_cache = build_alias_index(cfg)
    idx = _province_alias_cache
    t = norm_text(text)
    for a in sorted(idx, key=len, reverse=True):
        if len(a) >= 3 and a in t:
            return idx[a]
    return None


# ---- Time formatting ----

def format_minutes_human(mins) -> Optional[str]:
    """'XX min' | 'Xh Ym' | 'Nd Xh'"""
    if mins is None:
        return None
    try:
        m = float(mins)
    except (TypeError, ValueError):
        return None
    if m < 0:
        return None
    if m < 60:
        return f"{int(round(m))} min"
    if m < 1440:
        h, rm = int(m // 60), int(round(m % 60))
        return f"{h}h {rm}m" if rm else f"{h}h"
    d, rh = int(m // 1440), int(round((m % 1440) / 60))
    return f"{d}d {rh}h" if rh else f"{d}d"
