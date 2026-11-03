"""Lambda inference — wersja próbna (tracer).

Faza INIT (kod na poziomie modułu) wykonuje się raz na środowisko wykonawcze: ładuje spaCy.
Faza INVOKE (`handler`) wykonuje się przy każdym zapytaniu.

Zasady (AGENTS.md, ADR-0004, ADR-0006):
- w zmiennych globalnych tylko dane tylko do odczytu (model) — nigdy dane zapytań,
- nie logujemy surowego tekstu klienta, tylko jego długość i hash,
- twardy limit długości wejścia.
"""

import hashlib
import json
import os
import time

# ---------- INIT: raz na środowisko wykonawcze ----------
_import_started = time.perf_counter()
import spacy  # noqa: E402 — import mierzony osobno (tysiące plików bibliotek)

IMPORT_SECONDS = round(time.perf_counter() - _import_started, 3)

SPACY_MODEL = os.environ.get("SPACY_MODEL", "pl_core_news_lg")
_load_started = time.perf_counter()
NLP = spacy.load(SPACY_MODEL, disable=["ner", "textcat"])
INIT_SECONDS = round(time.perf_counter() - _load_started, 3)

print(json.dumps({"event": "init", "model": SPACY_MODEL, "import_seconds": IMPORT_SECONDS, "load_seconds": INIT_SECONDS}))

MAX_TEXT_CHARS = int(os.environ.get("MAX_TEXT_CHARS", "20000"))
SPACY_VERSION = spacy.__version__
MODEL_VERSION = NLP.meta.get("version", "unknown")

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
    if event.get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(raw).decode("utf-8")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    text = payload.get("text") if isinstance(payload, dict) else None
    return text if isinstance(text, str) else None


def handler(event, context):
    global _is_cold
    cold_start = _is_cold
    _is_cold = False

    text = _parse_text(event)
    if text is None or not text.strip():
        return _response(400, {"error": "Body musi być JSON-em z niepustym polem 'text'."})
    if len(text) > MAX_TEXT_CHARS:
        return _response(413, {"error": f"Tekst za długi (maks. {MAX_TEXT_CHARS} znaków)."})

    started = time.perf_counter()
    doc = NLP(text)
    tokens = [t for t in doc if not (t.is_space or t.is_punct)]
    sentences = list(doc.sents)
    processing_ms = round((time.perf_counter() - started) * 1000, 1)

    result = {
        "tracer": True,
        "stats": {
            "chars": len(text),
            "tokens": len(tokens),
            "sentences": len(sentences),
            "avg_sentence_tokens": round(len(tokens) / max(len(sentences), 1), 2),
            "noun_ratio": round(sum(t.pos_ == "NOUN" for t in tokens) / max(len(tokens), 1), 3),
        },
        "timing": {
            "cold_start": cold_start,
            "import_seconds": IMPORT_SECONDS if cold_start else None,
            "init_seconds": INIT_SECONDS if cold_start else None,
            "processing_ms": processing_ms,
        },
        "versions": {"spacy": SPACY_VERSION, "model": SPACY_MODEL, "model_version": MODEL_VERSION},
    }

    # Log bez treści tekstu (ADR-0006): długość, hash, czasy.
    print(json.dumps({
        "event": "evaluate",
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "chars": len(text),
        "cold_start": cold_start,
        "init_seconds": INIT_SECONDS if cold_start else None,
        "processing_ms": processing_ms,
        "request_id": getattr(context, "aws_request_id", None),
    }))

    return _response(200, result)
