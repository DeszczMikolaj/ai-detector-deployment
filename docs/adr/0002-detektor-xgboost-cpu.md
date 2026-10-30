# ADR-0002: Detektor — XGBoost na cechach stylometrycznych, CPU-only

- **Status:** przyjęta (stan obecny)
- **Data:** 2026-10-29

## Decyzja
Klasyfikator XGBoost na ~37 cechach (płytka stylometria, prawo Zipfa, dynamika nieliniowa RQA/CRQA/NVG/MSE). Preprocessing: spaCy `pl_core_news_lg` (tokenizacja, POS, morfologia, drzewo zależności). Pipeline nie używa embeddingów ani LLM.

## Konsekwencje
- Trening i inference działają na CPU; GPU niepotrzebne.
- Największy koszt inference: załadowanie spaCy `lg` (kilkaset MB RAM, kilka sekund) — raz na proces/środowisko.
- Wymagany twardy limit długości tekstu wejściowego w API (ochrona przed DoS).
- Train/serve skew: preprocessing + model wersjonowane jako jeden artefakt; ta sama wersja spaCy i modelu językowego w treningu i inference. Kod ekstrakcji cech wyłącznie w `packages/features/`.
- Do poprawy: stały seed dla szumu w NVG (determinizm cech); znany błąd przesunięcia kolumn w CSV (MTLD vs nagłówek).
