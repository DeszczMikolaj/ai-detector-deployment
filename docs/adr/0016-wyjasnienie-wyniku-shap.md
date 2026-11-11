# ADR-0016: Wyjaśnienie wyniku — top 5 cech wg SHAP w odpowiedzi API

- **Status:** przyjęta
- **Data:** 2026-11-11
- **Dotyczy:** ADR-0004 (inference na Lambdzie), ADR-0006 (logowanie zapytań), ADR-0007 (flaga OOD), ADR-0012 (artefakt modelu)

## Kontekst
Odpowiedź `POST /evaluate` zawierała tylko etykietę, prawdopodobieństwo i flagę OOD — UI nie mogło pokazać, **dlaczego** tekst dostał taką ocenę. XGBoost ma wbudowany TreeSHAP (`pred_contribs=True`), więc wyjaśnienie nie wymaga biblioteki `shap` ani zmian w obrazie.

Pomiar na modelu `v1` (898 drzew, głębokość 15), 200 prawdziwych próbek po jednej, 1 wątek, lokalnie:

| | p50 | p95 |
|---|---|---|
| predykcja | 0,3 ms | 0,4 ms |
| SHAP dokładny (TreeSHAP) | 17,7 ms | 23,9 ms |
| SHAP przybliżony (Saabas) | 3,4 ms | 4,9 ms |

Kontrola: suma wartości SHAP = logit modelu (0,2604 = 0,2604). Lambda (3008 MB, ~1,7 vCPU) jest zwykle 1,5–2× wolniejsza niż desktop → dokładny SHAP szacunkowo 35–48 ms.

## Decyzja
1. **Każda odpowiedź** zawiera pole `explanation`: metoda, `base_value` (wynik „średni” modelu w log-odds) i **5 cech o największym |SHAP|** dla tej próbki — nazwa cechy, jej wartość, wpływ SHAP (log-odds) i kierunek (`towards`: `ai` / `human`).
2. **Domyślnie TreeSHAP (dokładny).** Kryterium: koszt < 50 ms na zapytanie. Każde zapytanie loguje `shap_ms`; jeśli p95 w Lambdzie przekroczy 50 ms, przełączamy zmienną `SHAP_METHOD=approx` (Terraform: `inference_shap_method`) — bez zmiany kodu.
3. **Pełne 38 wartości SHAP** nie trafiają do odpowiedzi; trafią do wpisu logu zapytania razem z wektorem cech, gdy powstanie logowanie przez SQS (ADR-0006) — na potrzeby panelu admina.
4. **Ranking globalny:** `train.py` zapisuje w `metadata.json` ranking cech wg średniego |SHAP| na holdoucie (`feature_importance`). Lambda używa go do wyboru „najważniejszych cech” flagi OOD — zgodnie z ADR-0007. Artefakty bez rankingu (np. `v1`) używają rankingu `total_gain` z modelu.

## Uzasadnienie
- Wyjaśnienie wyniku zwiększa zaufanie do oceny i pomaga zespołowi wyłapać błędy modelu (np. ocena zdominowana przez długość tekstu).
- TreeSHAP jest dokładny i spójny (suma = wynik modelu); top 5 ogranicza odpowiedź do tego, co da się sensownie pokazać.
- Przełącznik metody daje zapasowy wariant bez kolejnego wdrożenia kodu.

## Konsekwencje / trade-offy
- **Latencja:** +~18–48 ms na zapytanie (dziś ~16 ms → ~35–65 ms przetwarzania w Lambdzie). Nadal pomijalne wobec sieci i API Gateway.
- **Czytelność:** nazwy cech (`Zipf_Slope`, `RQA_Determinism`) i log-odds nic nie mówią laikowi. **UI potrzebuje słownika cech po polsku** (krótki opis każdej z 38 cech) i prezentacji kierunku zamiast surowej liczby — do przygotowania przez zespół ML/frontend.
- **Ułatwienie obejścia detektora:** ujawnienie cech decydujących o wyniku podpowiada, jak przerobić tekst AI. Świadomie akceptujemy w projekcie studenckim; w produkcji rozważyć wyjaśnienia tylko dla zalogowanych lub zgrubne (kategorie cech zamiast wartości).
- **SHAP wyjaśnia model, nie rzeczywistość:** pokazuje, na co model patrzy, a nie dowodzi, że tekst jest AI. UI musi to komunikować.
- Zmiana kontraktu API (nowe pole) — wsteczna zgodność zachowana (pola tylko dodane).

## Rozważone alternatywy
| Opcja | Powód odrzucenia |
|---|---|
| Brak wyjaśnień | UI nie może uzasadnić wyniku |
| SHAP tylko na żądanie (`"explain": true`) | Koszt mieści się w budżecie — prostszy kontrakt bez parametru; wrócimy do tego, jeśli pomiar w Lambdzie przekroczy 50 ms także dla `approx` |
| Biblioteka `shap` | Większy obraz i cold start; XGBoost liczy TreeSHAP natywnie |
| Globalna ważność cech (ta sama dla każdej próbki) | Nie wyjaśnia konkretnego wyniku |
| Pełne 38 wartości w odpowiedzi | Nieczytelne dla użytkownika, większa odpowiedź; trafią do logów (ADR-0006) |
