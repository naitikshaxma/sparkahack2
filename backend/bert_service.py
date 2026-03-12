import pickle
from pathlib import Path
from typing import Tuple

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MODEL_PATH = Path("models/intent_model")
if not MODEL_PATH.exists():
    MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "intent_model"

tokenizer = AutoTokenizer.from_pretrained(str(MODEL_PATH), local_files_only=True)
model = AutoModelForSequenceClassification.from_pretrained(str(MODEL_PATH), local_files_only=True)
model.eval()

with open(MODEL_PATH / "label_encoder.pkl", "rb") as handle:
    label_encoder = pickle.load(handle)


def get_intent_model_status() -> dict:
    return {
        "model_path": str(MODEL_PATH),
        "loaded": True,
        "num_labels": int(model.config.num_labels),
        "label_count": int(len(label_encoder.classes_)),
    }


def predict_intent(text: str) -> Tuple[str, float]:
    clean_text = (text or "").strip()
    if not clean_text:
        return "unknown", 0.0

    inputs = tokenizer(
        clean_text,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=128,
    )

    with torch.no_grad():
        outputs = model(**inputs)

    probs = torch.softmax(outputs.logits, dim=1)
    idx = int(torch.argmax(probs, dim=1).item())
    return label_encoder.classes_[idx], probs[0][idx].item()
