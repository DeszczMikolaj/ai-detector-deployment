# `detector_features`

Ekstrakcja **38 cech** stylometrycznych z tekstu polskiego. **Jedyne źródło cech** dla treningu (`pipelines/retraining/`) i inference (`services/inference/`) — AGENTS.md, zasada 1; ADR-0002, ADR-0015.

Przeniesione z repozytorium `ai-text-recognition` (`src/preprocessing/`) z ustawieniami treningu: model spaCy `pl_core_news_md` 3.8.0, spaCy 3.8.13, bez lematyzacji, bez usuwania stop-words i interpunkcji, lowercase.

## Instalacja
```bash
pip install -e packages/features[test]
pip install https://github.com/explosion/spacy-models/releases/download/pl_core_news_md-3.8.0/pl_core_news_md-3.8.0-py3-none-any.whl
```

## Użycie
```python
from detector_features import load_nlp, extract, extract_many, FEATURE_NAMES, FEATURE_SCHEMA_VERSION

nlp = load_nlp()                         # raz na proces (kilka sekund)
vec = extract("Jakiś tekst.", nlp)       # np.ndarray (38,), kolejność = FEATURE_NAMES
X = extract_many(lista_tekstów, nlp)     # np.ndarray (n, 38)
```

## Kontrakt cech (schemat v2)
| Grupa | Cechy | Plik |
|---|---|---|
| Płytka stylometria (18) | `Token_Count` … `Yules_K`, **`MTLD`**, `Noun_Ratio` … `Max_Dep_Depth` | `stylometry.py` |
| Prawo Zipfa (6) | `Zipf_MAPE` … `Metric_R` | `zipf.py` |
| Dynamika nieliniowa (14) | `Taylor_b`, RQA ×4, CRQA ×4, NVG ×4, `MSE_Entropy_Variance` | `dynamics.py` |

Pełna lista i historia: `src/detector_features/schema.py`. **Każda zmiana nazwy, kolejności lub sposobu liczenia cechy = nowa `FEATURE_SCHEMA_VERSION` i ponowny trening.** Model z innym schematem nie może być serwowany (ADR-0012).

### Zmiany względem `ai-text-recognition` (schemat v1 → v2)
1. **MTLD ma swoją nazwę.** W v1 liczono 38 wartości, a nagłówek CSV miał 37 nazw — `pandas` robił z `Token_Count` indeks, a pierwsze 12 kolumn miało nazwy przesunięte o jedną (np. kolumna „`Dot_Ratio`” zawierała średnią długość zdania). Modele z v1 są niezgodne z v2.
2. **Deterministyczny szum w NVG** (`NVG_SEED = 42`) — ten sam tekst zawsze daje te same cechy.
3. **Regresja liniowa w numpy** zamiast `sklearn.LinearRegression` (ten sam OLS) — mniejszy obraz Lambdy.

### Weryfikacja zgodności (2026-11-05)
Na 4 tekstach testowych porównano wyniki z oryginalnym pipeline'em (`pl_core_news_md`, bez lematyzacji): **34 cechy identyczne** (maks. różnica względna ~1e-16), 4 cechy NVG różnią się do ~6% — oryginał dodawał szum bez ziarna, więc nie był powtarzalny nawet sam ze sobą.

## Testy
```bash
cd packages/features && pytest -q
```
Testy ekstrakcji pomijane, jeśli model `pl_core_news_md` nie jest zainstalowany.
