# Inference (Lambda)

`POST /evaluate` → cechy z `detector_features` → XGBoost → ocena „AI vs człowiek” + flaga OOD + wyjaśnienie wyniku (top 5 cech wg SHAP, ADR-0016).

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
  "explanation": {
    "method": "shap_exact",
    "base_value": 0.0412,
    "top_features": [
      {"feature": "Avg_Sent_Len", "value": 21.5, "shap": 0.8123, "towards": "ai"},
      {"feature": "Zipf_Slope", "value": -1.02, "shap": -0.3311, "towards": "human"}
    ]
  },
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
| `explanation.top_features` | 5 cech o największym wpływie na wynik tej próbki, malejąco wg \|`shap`\|. `value` = wartość cechy, `shap` = wpływ w skali log-odds, `towards` = klasa, w stronę której cecha przesuwa wynik (`null`, gdy wpływ = 0) |
| `explanation.base_value` | wynik „średni” modelu (log-odds); `base_value` + suma wszystkich 38 wartości SHAP = logit wyniku |

Błędy:
- `400` — body nie jest JSON-em z niepustym polem `text`,
- `413` — tekst dłuższy niż `MAX_TEXT_CHARS`,
- `500` — błąd liczenia cech.

**Najważniejsze cechy dla OOD:** ranking wg średniego |SHAP| z `metadata.json` (`feature_importance`, zapisuje go `train.py`). Artefakt `v1` go nie ma — wtedy ranking `total_gain` z modelu (log `init` → `ood_top_features_source`). Progi: `OOD_MIN_FEATURES`, `OOD_TOP_K`.

**Koszt wyjaśnienia (pomiar w Lambdzie, 2026-11-11, obraz `e044a90`, 3008 MB):** `shap_ms` 28,5–29,2 ms, `processing_ms` (cechy + predykcja + SHAP) ~48–50 ms warm. Kryterium ADR-0016 (< 50 ms na SHAP) spełnione — zostaje `SHAP_METHOD=exact`.

**Prezentacja w UI (ADR-0016):** nazwy cech i log-odds są nieczytelne dla użytkownika — UI potrzebuje słownika cech po polsku i powinno pokazywać kierunek („w stronę AI / człowieka”), nie surowe liczby. SHAP wyjaśnia, na co patrzy model, a nie dowodzi, że tekst jest AI.

## Zmienne środowiskowe
| Zmienna | Domyślnie | Opis |
|---|---|---|
| `MODEL_URI` | — (wymagana) | `s3://<bucket>/models/<wersja>/` albo katalog lokalny |
| `MODEL_WORKDIR` | `/tmp/model` | dokąd pobrać artefakt z S3 |
| `MAX_TEXT_CHARS` | `20000` | limit długości tekstu |
| `SHAP_METHOD` | `exact` | `exact` (TreeSHAP) albo `approx` (Saabas, ~5× szybsza) — ADR-0016 |
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
