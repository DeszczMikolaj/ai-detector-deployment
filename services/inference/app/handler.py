"""Lambda inference: tekst → cechy (detector_features) → XGBoost → ocena AI vs człowiek.

Faza INIT (kod na poziomie modułu) wykonuje się raz na środowisko wykonawcze:
ładuje spaCy, pobiera model championa z S3 (MODEL_URI) i go weryfikuje (ADR-0012).
Faza INVOKE (`handler`) wykonuje się przy każdym zapytaniu.

Zasady (AGENTS.md, ADR-0004, ADR-0006):
- w zmiennych globalnych tylko dane tylko do odczytu (modele) — nigdy dane zapytań,
- nie logujemy surowego tekstu klienta, tylko jego długość i hash,
- twardy limit długości wejścia.
"""

import base64
import hashlib
import json
import os
import time
from pathlib import Path

# ---------- INIT: raz na środowisko wykonawcze ----------
_t0 = time.perf_counter()
from detector_features import DEFAULT_SPACY_MODEL, FEATURE_SCHEMA_VERSION, extract, load_nlp  # noqa: E402 — importy mierzone

from app import artifact  # noqa: E402

IMPORT_SECONDS = round(time.perf_counter() - _t0, 3)

SPACY_MODEL = os.environ.get("SPACY_MODEL", DEFAULT_SPACY_MODEL)
MODEL_URI = os.environ["MODEL_URI"]  # brak = błąd init; Lambda bez modelu nie powinna przyjmować ruchu
MAX_TEXT_CHARS = int(os.environ.get("MAX_TEXT_CHARS", "20000"))
SHAP_METHOD = os.environ.get("SHAP_METHOD", "exact")  # ADR-0016

_t0 = time.perf_counter()
NLP = load_nlp(SPACY_MODEL)
SPACY_LOAD_SECONDS = round(time.perf_counter() - _t0, 3)

_t0 = time.perf_counter()
MODEL = artifact.load(
    MODEL_URI,
    spacy_model=SPACY_MODEL,
    spacy_model_version=NLP.meta.get("version", "unknown"),
    workdir=Path(os.environ.get("MODEL_WORKDIR", "/tmp/model")),
    shap_method=SHAP_METHOD,
)
MODEL_LOAD_SECONDS = round(time.perf_counter() - _t0, 3)

INIT_SECONDS = round(IMPORT_SECONDS + SPACY_LOAD_SECONDS + MODEL_LOAD_SECONDS, 3)

print(json.dumps({
    "event": "init",
    "model_version": MODEL.version,
    "feature_schema_version": FEATURE_SCHEMA_VERSION,
    "spacy_model": SPACY_MODEL,
    "trained_with_xgboost": MODEL.metadata.get("xgboost_version"),
    "shap_method": MODEL.shap_method,
    "ood_top_features_source": MODEL.top_features_source,
    "import_seconds": IMPORT_SECONDS,
    "spacy_load_seconds": SPACY_LOAD_SECONDS,
    "model_load_seconds": MODEL_LOAD_SECONDS,
}))

# True tylko dla pierwszego wywołania w danym środowisku (cold start).
_is_cold = True


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _parse_text(event: dict) -> str | None:
    raw = event.get("body") or ""
    try:
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        payload = json.loads(raw)
    except (ValueError, TypeError):  # JSONDecodeError i UnicodeDecodeError dziedziczą po ValueError
        return None
    text = payload.get("text") if isinstance(payload, dict) else None
    return text if isinstance(text, str) else None


def handler(event, context):
    global _is_cold
    cold_start = _is_cold
    _is_cold = False
    request_id = getattr(context, "aws_request_id", None)

    text = _parse_text(event)
    if text is None or not text.strip():
        return _response(400, {"error": "Body musi być JSON-em z niepustym polem 'text'."})
    if len(text) > MAX_TEXT_CHARS:
        return _response(413, {"error": f"Tekst za długi (maks. {MAX_TEXT_CHARS} znaków)."})

    text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    started = time.perf_counter()
    try:
        prediction = MODEL.predict(extract(text, NLP))
    except Exception as exc:  # noqa: BLE001 — log bez treści tekstu, klient dostaje 500
        print(json.dumps({"event": "error", "error_type": type(exc).__name__, "text_sha256": text_sha256, "request_id": request_id}))
        return _response(500, {"error": "Nie udało się ocenić tekstu."})
    processing_ms = round((time.perf_counter() - started) * 1000, 1)

    result = {
        "label": prediction.label,
        "ai_probability": round(prediction.ai_probability, 4),
        "threshold": MODEL.threshold,
        "out_of_distribution": prediction.out_of_distribution,
        "ood_features": list(prediction.ood_features),
        "explanation": {
            "method": f"shap_{MODEL.shap_method}",
            "base_value": round(prediction.base_value, 4),
            "top_features": [
                {"feature": c.feature, "value": round(c.value, 4), "shap": round(c.shap, 4), "towards": c.towards}
                for c in prediction.top_contributions
            ],
        },
        "model_version": MODEL.version,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "timing": {
            "cold_start": cold_start,
            "init_seconds": INIT_SECONDS if cold_start else None,
            "processing_ms": processing_ms,
        },
    }

    # Log bez treści tekstu (ADR-0006): hash, długość, wynik, czasy.
    print(json.dumps({
        "event": "evaluate",
        "text_sha256": text_sha256,
        "chars": len(text),
        "label": prediction.label,
        "ai_probability": result["ai_probability"],
        "out_of_distribution": prediction.out_of_distribution,
        "ood_feature_count": len(prediction.ood_features),
        "model_version": MODEL.version,
        "cold_start": cold_start,
        "init_seconds": INIT_SECONDS if cold_start else None,
        "processing_ms": processing_ms,
        "shap_ms": round(prediction.shap_ms, 1),
        "shap_method": MODEL.shap_method,
        "top_features": [c.feature for c in prediction.top_contributions],
        "request_id": request_id,
    }))

    return _response(200, result)
