# Inference (Lambda)

`POST /evaluate` → cechy z `detector_features` → XGBoost → ocena „AI vs człowiek” + flaga OOD.

- **Obraz** zawiera kod, zależności (`xgboost-cpu`, spaCy) i model spaCy `pl_core_news_md` (ADR-0015).
- **Model XGBoost** jest pobierany z S3 przy cold starcie (`MODEL_URI`, ADR-0012). Faza init sprawdza:
  - sumy SHA-256 z `checksums.json`,
  - wersję schematu cech i listę cech z `metadata.json` względem `detector_features` w obrazie,
  - nazwę i wersję modelu spaCy względem tego, na którym trenowano.

  Przy niezgodności init kończy się błędem i wersja nie przyjmuje ruchu.

## Kontrakt API
Zapytanie:
```json
{"text": "Tekst do oceny…"}
```
Odpowiedź `200`:
```json
{
  "label": "ai",
  "ai_probability": 0.9132,
  "threshold": 0.5,
  "out_of_distribution": false,
  "ood_features": ["Zipf_Slope"],
  "model_version": "v1",
  "feature_schema_version": "2",
  "timing": {"cold_start": false, "init_seconds": null, "processing_ms": 85.3}
}
```

| Pole | Znaczenie |
|---|---|
| `label` | `ai` albo `human`. Wynik porównania `ai_probability` z progiem `threshold` z `metadata.json` |
| `ood_features` | cechy poza zakresem p1–p99 ze zbioru treningowego |
| `out_of_distribution` | `true`, gdy w `ood_features` są ≥ 3 cechy albo co najmniej jedna z 5 najważniejszych cech modelu (ADR-0007) |

Błędy:
- `400` — body nie jest JSON-em z niepustym polem `text`,
- `413` — tekst dłuższy niż `MAX_TEXT_CHARS`,
- `500` — błąd liczenia cech.

**Uwaga do OOD:** ADR-0007 mówi o najważniejszych cechach według SHAP. Tymczasem używamy rankingu `total_gain` z samego modelu, bo artefakt `v1` nie zawiera rankingu SHAP. Progi można zmienić zmiennymi `OOD_MIN_FEATURES` i `OOD_TOP_K`.

## Zmienne środowiskowe
| Zmienna | Domyślnie | Opis |
|---|---|---|
| `MODEL_URI` | — (wymagana) | `s3://<bucket>/models/<wersja>/` albo katalog lokalny |
| `MODEL_WORKDIR` | `/tmp/model` | dokąd pobrać artefakt z S3 |
| `MAX_TEXT_CHARS` | `20000` | limit długości tekstu |
| `SPACY_MODEL` | `pl_core_news_md` | ustawiana w obrazie |

## Testy (z katalogu `services/inference`)
```powershell
pip install -r requirements.txt -r requirements-dev.txt ..\..\packages\features
pytest -q
```
Testy budują mały artefakt na losowych danych. Testy handlera są pomijane, jeśli nie ma modelu `pl_core_news_md`.

## Test z prawdziwym modelem, przed budowaniem obrazu
Uruchom w środowisku treningowym, z katalogu głównego repo. Sprawdza, czy artefakt z `train.py` przechodzi weryfikację w handlerze:
```powershell
pip install xgboost-cpu==3.4.1   # lub zostaw xgboost z treningu
$env:MODEL_URI = "artifacts\model-v1"
$env:PYTHONPATH = "services\inference"
python -c "import json; from app.handler import handler; print(handler({'body': json.dumps({'text': 'Wczoraj wieczorem poszedłem do kina. Film był długi, ale bardzo ciekawy.'})}, None)['body'])"
```

## Budowanie i wdrożenie
Patrz `infra/terraform/envs/dev/README.md`. Obraz budujemy **z katalogu głównego repo**, bo kontekst musi zawierać `packages/features`:
```powershell
docker build --platform linux/amd64 --provenance=false -f services/inference/Dockerfile -t "${repo}:$tag" .
```
