# ADR-0010: Workery pipeline'u — CPU na Spot, GPU opcjonalne, On-Demand jako tryb awaryjny

- **Status:** przyjęta
- **Data:** 2026-10-31
- **Doprecyzowuje:** ADR-0003 (zasoby obliczeniowe pipeline'u)
- **Zastępuje częściowo:** ADR-0001 — konsekwencję „generacja wymaga GPU” (sama decyzja o lokalnych LLM-ach obowiązuje)

## Kontekst
ADR-0001 zakładał, że generacja lokalnymi LLM-ami wymaga GPU. Nowe konta AWS mają quotę 0 vCPU dla instancji G/VT, a jej podniesienie jest niepewne. Docelowo jedno uruchomienie pipeline'u generuje **setki** próbek.

Spike (2026-10-31, i7-13700F, 32 GB DDR4-2133, Ollama, `qwen2.5:7b` Q4, tylko CPU):

| Metryka | Wartość |
|---|---|
| eval rate | 6,3 tokena/s |
| próbka ~300 słów po polsku | ~710 tokenów, ~1 min 58 s |
| ładowanie modelu | ~5 s (raz na job) |

Generacja na CPU jest ograniczona przepustowością RAM (pułap ≈ przepustowość / rozmiar modelu: ~34 GB/s / ~4,7 GB ≈ 7 tok/s), nie liczbą rdzeni.

## Decyzja
1. **Workery generacji działają na CPU** (modele ~7–8B w kwantyzacji 4-bit, np. llama.cpp / Ollama). GPU to opcjonalne przyspieszenie — ten sam obraz, inna definicja joba / compute environment.
2. **Domyślnie Spot**, z odpornością na przerwania:
   - array job, porcje po ~25 próbek;
   - każda próbka zapisywana do S3 od razu pod deterministycznym kluczem; restart pomija gotowe (idempotencja);
   - `retryStrategy` (do 10 prób — limit AWS Batch) ograniczone do przerwań Spot; nieudane porcje pipeline może zlecić ponownie.
3. **Dwie osobne kolejki AWS Batch:** `spot` (domyślna) i `ondemand` (awaryjna). Bez automatycznego fallbacku w ramach jednej kolejki — przy braku pojemności Spot joby potrafią wisieć w `RUNNABLE` zamiast przejść dalej.
4. **Widoczny przełącznik w panelu admina** „tryb awaryjny: On-Demand” wybiera kolejkę przy uruchomieniu pipeline'u. Optymalizacja kosztów jest świadomie pokazana, nie ukryta.
5. **Alarm:** joby w `RUNNABLE` dłużej niż ~15 min są anulowane (`jobStateTimeLimitActions`) i sygnalizowane adminowi.
6. **Pojemność jako konfiguracja:** maksymalna liczba vCPU workerów = `maxvCpus` compute environmentu (start: 14, po podniesieniu quoty: więcej). Równoległość skraca czas przy tym samym koszcie.

## Uzasadnienie
- Przy setkach próbek CPU + równoległość wystarcza: ~1–2 h na uruchomienie przy 4 workerach, koszt rzędu kilku USD (szacunek do weryfikacji pomiarem na AWS; instancje z DDR5 powinny być szybsze niż pomiar na DDR4-2133).
- Projekt nie jest zablokowany decyzją AWS o quocie GPU.
- Spot jest wyraźnie tańszy; przerwanie wydłuża tylko czas pipeline'u, nie dotyka użytkowników końcowych (praca wsadowa, nie latencja zapytań).

## Konsekwencje / trade-offy
- **Jakość danych:** generatory ~8B piszą po polsku słabiej niż modele komercyjne — detektor może uczyć się wykrywać słabsze modele. Łagodzenie: kilka rodzin modeli (np. PLLuM, Bielik, Qwen); ograniczenie opisane w raporcie.
- Pipeline musi być idempotentny i podzielny na porcje — wymaganie dla implementacji.
- **Na prezentację:** uruchomienie od razu w trybie On-Demand (różnica kosztu rzędu centów, brak ryzyka wiszących jobów).
- Quoty (eu-central-1): Standard On-Demand obecnie 16 vCPU — wniosek o 40 (On-Demand i Spot). Wniosek o G/VT (4 vCPU) składamy mimo to, jako nice to have.

## Rozważone alternatywy
| Opcja | Powód odrzucenia |
|---|---|
| GPU jako warunek konieczny | Niepewna quota, blokuje projekt |
| Modele 1–3B na CPU | Szybsze, ale słaba polszczyzna → gorsze dane treningowe |
| Jedna kolejka Spot → On-Demand z automatycznym fallbackiem | Zawodne przy braku pojemności Spot (joby wiszą w `RUNNABLE`) |
| Tylko On-Demand | Wyższy koszt bez realnej korzyści dla pracy wsadowej |
