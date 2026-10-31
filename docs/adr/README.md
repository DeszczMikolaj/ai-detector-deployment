# Decyzje architektoniczne (ADR)

Format: decyzja → uzasadnienie → konsekwencje / trade-offy. Przyjętych ADR nie edytujemy — zastępujemy nowym.

| Nr | Tytuł | Status |
|----|-------|--------|
| [0001](0001-generator-lokalne-llm.md) | Generator próbek AI — lokalne LLM-y | przyjęta (konsekwencja „wymaga GPU” zastąpiona przez 0010) |
| [0002](0002-detektor-xgboost-cpu.md) | Detektor — XGBoost na cechach stylometrycznych, CPU-only | przyjęta |
| [0003](0003-efemeryczny-pipeline.md) | Ciężki pipeline na efemerycznych zasobach | przyjęta co do zasady (doprecyzowana przez 0010) |
| [0004](0004-inference-lambda.md) | Inference — Lambda (container image) za API Gateway | przyjęta |
| [0005](0005-admin-ec2-compose.md) | Panel admina — EC2 + Docker Compose | przyjęta |
| [0006](0006-logowanie-sqs.md) | Logowanie zapytań przez SQS, bez surowego tekstu | przyjęta |
| [0007](0007-drift-ood.md) | Monitoring driftu i flaga OOD | przyjęta |
| [0008](0008-konto-koszty-aws.md) | Konto i koszty AWS | rekomendacja |
| [0009](0009-monorepo-repo-prywatne.md) | Monorepo na prywatnym koncie GitHub | przyjęta |
| [0010](0010-workery-cpu-spot.md) | Workery pipeline'u — CPU na Spot, GPU opcjonalne, On-Demand jako tryb awaryjny | przyjęta |

Lustro do przeglądania: Confluence, przestrzeń TAI-DETEKTOR → Architektura → Decyzje architektoniczne (ADR). **Źródłem prawdy jest to repozytorium.**

## Odstępstwa od `kontekst-projektu.md`
- Dodanie próbek nie uruchamia automatycznie retrainingu: próbki trafiają do stanu `pending`, retraining uruchamia admin lub próg N nowych próbek (do potwierdzenia przy projektowaniu pipeline'u).

## Backlog (must have)
- Bramka walidacji schematu cech w pipeline retrainingu (liczba, kolejność, typy, zakresy kolumn) przed porównaniem champion vs challenger.
- Włączenie ochrony gałęzi `main` (ADR-0009).
- Wnioski o quoty w eu-central-1: Standard On-Demand i Spot → 40 vCPU; G and VT On-Demand i Spot → 4 vCPU (nice to have) (ADR-0010).
- Pipeline generacji idempotentny i podzielny na porcje; dwie kolejki Batch (`spot`, `ondemand`) i przełącznik trybu awaryjnego w panelu admina (ADR-0010).
