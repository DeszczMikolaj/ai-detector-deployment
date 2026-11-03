# ADR-0015: Model spaCy `pl_core_news_md` zamiast `lg` (warunek utrzymania inference na Lambdzie)

- **Status:** proponowana — czeka na decyzję zespołu ML (przetrenowanie i porównanie jakości)
- **Data:** 2026-11-03
- **Dotyczy:** ADR-0002 (detektor, spaCy `lg`), ADR-0004 (inference na Lambdzie)
- **Podstawa:** [spike z 2026-11-03](../spikes/2026-11-03-inference-lambda-cold-start.md)

## Kontekst
Spike wykazał, że Lambda z `pl_core_news_lg` ma cold start > 60 s (samo `spacy.load` ~51 s), co przekracza limit API Gateway (29 s) — każde zapytanie trafiające na nowe środowisko kończy się błędem. Przyczyną jest ilość danych modelu czytanych przy starcie z leniwie podłączanego obrazu, nie CPU. Ten sam test z `pl_core_news_md`: `spacy.load` 3,2 s, pierwszy cold start nowego obrazu ~14,5 s, warm 120–200 ms end-to-end. Pamięci Lambdy na tym koncie nie da się zwiększyć ponad 3008 MB.

## Proponowana decyzja
1. Pipeline cech (trening i inference) przechodzi na **`pl_core_news_md` 3.8.0** (spaCy 3.8.13), pod warunkiem że po przetrenowaniu klasyfikatora jakość jest akceptowalna.
2. **Kryterium akceptacji** (do potwierdzenia przez zespół ML w ramach briefu retrainingu, pytania 18–22): metryka główna na tym samym zbiorze testowym nie gorsza od modelu na `lg` o więcej niż ustalony próg (np. 1 p.p.), bez istotnej regresji per domena.
3. Jeśli kryterium nie jest spełnione → zostajemy przy `lg`, a inference przenosimy na **stale działający kontener** (ECS Fargate z min. 1 zadaniem i autoskalowaniem, albo kontener na EC2 obok admin-api) — nowy ADR zastępujący ADR-0004.

## Konsekwencje
- **Przy przyjęciu:** ADR-0004 (Lambda) pozostaje w mocy; ADR-0002 zmienia model spaCy z `lg` na `md` — wymagany ponowny trening, nowy profil cech (ADR-0007) i nowa wersja modelu (ADR-0012). Obraz Lambdy ~1,3 GB zamiast ~2,4 GB.
- **Ryzyko jakości:** `md` ma mniejsze wektory słów → POS, morfologia i drzewo zależności mogą być nieco mniej dokładne, a ~37 cech na nich bazuje.
- **Ryzyko cold startu:** pierwszy start nowego obrazu nadal przekracza limit fazy init (10 s) i trwa ~14,5 s. Do zmierzenia: kolejne cold starty i wpływ pełnego pipeline'u cech. Łagodzenie na prezentację: rozgrzanie / provisioned concurrency (ADR-0004).

## Rozważone alternatywy
| Opcja | Uwagi |
|---|---|
| Lambda + `lg` | Odrzucone pomiarem: cold start > 60 s |
| Lambda + `lg` + provisioned concurrency | Brak cold startu tylko w zakresie rozgrzanych środowisk (~$30/mies. każde); skok ruchu ponad nie znów daje > 60 s |
| Lambda + `pl_core_news_sm` | Jeszcze szybsza, ale bez wektorów słów — większe ryzyko spadku jakości cech; do rozważenia, jeśli `md` nie wystarczy na Lambdzie |
| Stały kontener z `lg` (Fargate / EC2) | Brak cold startu dla użytkownika i brak zmiany modelu; koszt stały ~$15–40/mies., na EC2 bez autoskalowania |
