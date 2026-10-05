import os, sys, json
from pathlib import Path
import torch
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModelForSequenceClassification

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from src.train.vietnamese import segment_for_phobert

MODEL_DIR = os.path.join(PROJECT_ROOT, "data", "outputs", "checkpoints", "stage1_risk_any")
CLEAN_JSONL = os.path.join(PROJECT_ROOT, "data", "clean", "articles_clean.jsonl")
OUT_PRED = os.path.join(PROJECT_ROOT, "data", "outputs", "predictions.jsonl")
MAX_LEN = 256
BATCH_SIZE = 16

def iter_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

def main():
    if not os.path.isdir(MODEL_DIR):
        raise FileNotFoundError(f"PhoBERT checkpoint missing: {MODEL_DIR}. Run python -m src.train.train first.")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(MODEL_DIR, use_fast=False)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR).to(device)
    model.eval()

    os.makedirs(os.path.dirname(OUT_PRED), exist_ok=True)
    temporary = OUT_PRED + ".tmp"
    with open(temporary, "w", encoding="utf-8") as out, torch.inference_mode():
        batch = []

        def write_batch(rows):
            texts = [segment_for_phobert(((r.get("title") or "") + "\n\n" + (r.get("text") or "")).strip()) for r in rows]
            enc = tok(texts, truncation=True, max_length=MAX_LEN, padding=True, return_tensors="pt")
            enc = {k: v.to(device) for k, v in enc.items()}
            probabilities = torch.sigmoid(model(**enc).logits.view(-1).float()).cpu().tolist()
            for row, probability in zip(rows, probabilities):
                out.write(json.dumps({
                    "id": row["id"], "p_risk_any": float(probability), "model_source": "phobert",
                }, ensure_ascii=False) + "\n")

        for row in tqdm(iter_jsonl(CLEAN_JSONL), desc="PhoBERT inference"):
            if row.get("id") and (row.get("title") or row.get("text")):
                batch.append(row)
            if len(batch) >= BATCH_SIZE:
                write_batch(batch)
                batch = []
        if batch:
            write_batch(batch)

    Path(temporary).replace(OUT_PRED)
    print("Wrote:", OUT_PRED)

if __name__ == "__main__":
    main()
