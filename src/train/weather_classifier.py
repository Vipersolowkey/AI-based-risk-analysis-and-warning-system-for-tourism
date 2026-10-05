"""Train the weather risk model from the included labeled weather dataset.

The target is risk_level_num (0..4); extreme disaster level 5 remains guarded
by HybridSafetyPredictor safety rules. A year-based holdout checks whether the
model generalizes to later dates rather than memorizing a random row split.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, classification_report, confusion_matrix
from xgboost import XGBClassifier

from src.api.weather_ai import LOCATION_ENCODING_MAP


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "src" / "integrations" / "weather" / "FINAL_DATASET_WITH_RISK-2.csv"
FEATURE_NAMES = ROOT / "src" / "integrations" / "weather" / "model_features.json"
MODEL_OUT = ROOT / "src" / "integrations" / "weather" / "weather_risk_v5_classifier.pkl"
METRICS_OUT = ROOT / "src" / "integrations" / "weather" / "weather_risk_v5_metrics.json"


def _location_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower().replace("đ", "d"))
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", plain)


def build_features(rows: pd.DataFrame) -> pd.DataFrame:
    """Match the API's feature engineering and province encoder exactly."""
    columns = json.loads(FEATURE_NAMES.read_text(encoding="utf-8"))
    province_codes = {_location_key(name): code for name, code in LOCATION_ENCODING_MAP.items()}
    province_codes["hochiminhcity"] = LOCATION_ENCODING_MAP["TP. Hồ Chí Minh"]
    names = rows["province"].map(_location_key)
    missing = sorted(set(names) - set(province_codes))
    if missing:
        raise ValueError(f"Weather dataset provinces missing from encoder: {missing}")

    frame = pd.DataFrame(index=rows.index)
    for column in columns:
        frame[column] = rows[column] if column in rows else 0.0
    frame["location_encoded"] = names.map(province_codes).astype(int)
    frame["slippery_index"] = ((rows["precipitation"] / 50.0).clip(upper=1.0) * (rows["humidity"] / 100.0)).round(4)
    frame["visibility_block"] = (1.0 - rows["visibility_km"] / 10.0).clip(lower=0.0).round(4)
    frame["smog_impact"] = (rows["pm25"] / 150.0).clip(upper=1.0).round(4)
    frame["vehicle_type"] = 0
    frame["hour_of_day"] = pd.to_datetime(rows["time"], format="mixed", errors="coerce").dt.hour.fillna(12)
    return frame[columns].astype(float)


def train() -> dict:
    rows = pd.read_csv(DATASET)
    dates = pd.to_datetime(rows["time"], format="mixed", errors="coerce")
    train_mask = dates.dt.year < 2025
    validation_mask = dates.dt.year == 2025
    if not train_mask.any() or not validation_mask.any():
        raise ValueError("Expected weather rows from both 2023–2024 and 2025")

    features = build_features(rows)
    labels = rows["risk_level_num"].astype(int)
    train_labels = labels.loc[train_mask]
    counts = train_labels.value_counts()
    weights = train_labels.map(lambda label: np.sqrt(counts.max() / counts[label])).to_numpy()

    model = XGBClassifier(
        objective="multi:softprob", num_class=5, n_estimators=240,
        max_depth=6, learning_rate=0.06, subsample=0.85,
        colsample_bytree=0.9, tree_method="hist", device="cpu",
        n_jobs=4, random_state=42,
    )
    model.fit(features.loc[train_mask], train_labels, sample_weight=weights, verbose=False)
    truth = labels.loc[validation_mask]
    predicted = model.predict(features.loc[validation_mask])
    report = classification_report(truth, predicted, labels=[0, 1, 2, 3, 4],
                                   output_dict=True, zero_division=0)
    severe = truth >= 3
    severe_recall = float(((predicted >= 3) & severe).sum() / severe.sum()) if severe.any() else 0.0
    metrics = {
        "model_type": "XGBClassifier",
        "train_years": [2023, 2024],
        "validation_year": 2025,
        "train_rows": int(train_mask.sum()),
        "validation_rows": int(validation_mask.sum()),
        "balanced_accuracy": round(float(balanced_accuracy_score(truth, predicted)), 4),
        "macro_f1": round(float(report["macro avg"]["f1-score"]), 4),
        "severe_recall_levels_3_4": round(severe_recall, 4),
        "per_level": {str(i): {
            "precision": round(float(report[str(i)]["precision"]), 4),
            "recall": round(float(report[str(i)]["recall"]), 4),
            "f1": round(float(report[str(i)]["f1-score"]), 4),
            "support": int(report[str(i)]["support"]),
        } for i in range(5)},
        "confusion_matrix": confusion_matrix(truth, predicted, labels=[0, 1, 2, 3, 4]).tolist(),
    }
    joblib.dump(model, MODEL_OUT, compress=3)
    METRICS_OUT.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metrics


if __name__ == "__main__":
    print(json.dumps(train(), ensure_ascii=False, indent=2))
