"""Train and run a lightweight Vietnamese news risk classifier.

PhoBERT predictions in data/outputs/predictions.jsonl take precedence in the
API. This baseline supplies real model probabilities when no PhoBERT checkpoint
is available, using the same labeled stage-1 dataset and clean article text.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_fscore_support
from sklearn.pipeline import Pipeline


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = ROOT / "data" / "models" / "news_risk_tfidf.joblib"
DEFAULT_PREDICTIONS = ROOT / "data" / "outputs" / "news_baseline_predictions.jsonl"
DEFAULT_METRICS = ROOT / "data" / "models" / "news_risk_tfidf_metrics.json"


def _read_labeled(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, usecols=["id", "input_text", "label"])
    frame = frame.dropna(subset=["id", "input_text", "label"])
    frame = frame.drop_duplicates(subset=["id"]).drop_duplicates(subset=["input_text"])
    frame["label"] = frame["label"].astype(int)
    return frame


def train(model_path: Path = DEFAULT_MODEL, metrics_path: Path = DEFAULT_METRICS) -> dict:
    train_rows = _read_labeled(ROOT / "data" / "datasets" / "stage1_train.csv")
    validation = _read_labeled(ROOT / "data" / "datasets" / "stage1_val.csv")
    # The supplied splits have a few duplicated articles. Exclude them from
    # validation so the reported result is not helped by exact train copies.
    validation = validation[
        ~validation["id"].isin(train_rows["id"])
        & ~validation["input_text"].isin(train_rows["input_text"])
    ]
    if train_rows.empty or validation.empty:
        raise ValueError("Training or independent validation data is empty")

    classifier = Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2), min_df=3, max_features=60000,
            sublinear_tf=True,
        )),
        ("logreg", LogisticRegression(
            solver="liblinear", class_weight="balanced", max_iter=1000,
        )),
    ])
    classifier.fit(train_rows["input_text"].astype(str), train_rows["label"])
    probability = classifier.predict_proba(validation["input_text"].astype(str))[:, 1]
    predicted = (probability >= 0.5).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        validation["label"], predicted, average="binary", zero_division=0,
    )
    metrics = {
        "model_source": "tfidf_logreg",
        "train_articles": int(len(train_rows)),
        "validation_articles": int(len(validation)),
        "threshold": 0.5,
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "average_precision": round(float(average_precision_score(validation["label"], probability)), 4),
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(classifier, model_path, compress=3)
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metrics


def predict_articles(model_path: Path = DEFAULT_MODEL, output_path: Path = DEFAULT_PREDICTIONS) -> int:
    classifier = joblib.load(model_path)
    clean_path = ROOT / "data" / "clean" / "articles_clean.jsonl"
    articles = []
    with clean_path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                row = json.loads(line)
                article_id = row.get("id")
                if article_id:
                    articles.append((article_id, f"{row.get('title') or ''}\n\n{row.get('text') or ''}"))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        for start in range(0, len(articles), 256):
            batch = articles[start:start + 256]
            probability = classifier.predict_proba([text for _, text in batch])[:, 1]
            for (article_id, _), value in zip(batch, probability):
                output.write(json.dumps({
                    "id": article_id,
                    "p_risk_any": round(float(value), 6),
                    "model_source": "tfidf_logreg",
                }, ensure_ascii=False) + "\n")
    temporary.replace(output_path)
    return len(articles)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predict-only", action="store_true", help="Reuse a trained model for new clean articles")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--metrics-path", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--predictions-path", type=Path, default=DEFAULT_PREDICTIONS)
    args = parser.parse_args()
    if not args.predict_only:
        print("Validation:", train(args.model_path, args.metrics_path))
    print("Scored articles:", predict_articles(args.model_path, args.predictions_path))


if __name__ == "__main__":
    main()
