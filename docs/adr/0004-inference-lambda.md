# ADR-0004: Inference — AWS Lambda (container image) za API Gateway

- **Status:** przyjęta
- **Data:** 2026-10-29

## Decyzja
Endpoint oceny tekstu działa jako Lambda z obrazu kontenera (spaCy + model zapieczone w obrazie), za API Gateway.

## Uzasadnienie
Automatyczne skalowanie bez stałego kosztu; zmiana pojemności przez konfigurację (reserved concurrency) zamiast zmiany instancji i downtime'u. Throttling API Gateway pełni rolę rate limitera.

## Konsekwencje / trade-offy
- Cold start (kilka sekund) przy tworzeniu nowego środowiska wykonawczego. Model ładowany w fazie init (poza handlerem), raz na środowisko.
- Zakaz przechowywania danych zapytań w zmiennych globalnych i `/tmp` (współdzielone między wywołaniami w tym samym środowisku).
- Promocja / rollback modelu = przełączenie aliasu Lambdy (champion).
- Prezentacja (ruch skokowy po bezczynności = najgorszy przypadek): provisioned concurrency lub ręczny warm-up przed demo.
- Monitorujemy p50/p95/p99 latencji i liczbę cold startów, nie tylko średnią.
- Do zrobienia: spike — pomiar czasu `spacy.load` i `transform` dla typowego tekstu, pomiar cold startu na Lambdzie.
