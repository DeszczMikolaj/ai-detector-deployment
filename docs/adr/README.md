# Decyzje architektoniczne (ADR)

Format: decyzja → uzasadnienie → konsekwencje / trade-offy. Przyjętych ADR nie edytujemy — zastępujemy nowym.

| Nr | Tytuł | Status |
|----|-------|--------|
| [0001](0001-generator-lokalne-llm.md) | Generator próbek AI — lokalne LLM-y | przyjęta (konsekwencja „wymaga GPU” zastąpiona przez 0010) |
| [0002](0002-detektor-xgboost-cpu.md) | Detektor — XGBoost na cechach stylometrycznych, CPU-only | przyjęta (model spaCy `lg` zastąpiony `md` przez 0015) |
| [0003](0003-efemeryczny-pipeline.md) | Ciężki pipeline na efemerycznych zasobach | przyjęta co do zasady (doprecyzowana przez 0010) |
| [0004](0004-inference-lambda.md) | Inference — Lambda (container image) za API Gateway | przyjęta („model w obrazie” zastąpiony przez 0012) |
| [0005](0005-admin-ec2-compose.md) | Panel admina — EC2 + Docker Compose | przyjęta (wybór FastAPI zastąpiony przez 0011) |
| [0006](0006-logowanie-sqs.md) | Logowanie zapytań przez SQS, bez surowego tekstu | przyjęta |
| [0007](0007-drift-ood.md) | Monitoring driftu i flaga OOD | przyjęta |
| [0008](0008-konto-koszty-aws.md) | Konto, region (`eu-north-1`) i koszty AWS | przyjęta |
| [0009](0009-monorepo-repo-prywatne.md) | Monorepo na prywatnym koncie GitHub | przyjęta |
| [0010](0010-workery-cpu-spot.md) | Workery pipeline'u — CPU na Spot, GPU opcjonalne, On-Demand jako tryb awaryjny | przyjęta |
| [0011](0011-backend-admina-spring.md) | Backend admina w Spring Boot + Spring Security; Python tylko w części ML | przyjęta |
| [0012](0012-model-championa-z-s3.md) | Model championa ładowany z S3; obraz Lambdy zawiera tylko kod i spaCy | przyjęta |
| [0013](0013-status-jobow-eventbridge-sqs.md) | Status jobów przez EventBridge i SQS (publisher–subscriber) | przyjęta |
| [0014](0014-lustro-wag-llm-s3.md) | Lustro wag lokalnych LLM w S3 z przypiętymi wersjami | przyjęta |
| [0015](0015-model-spacy-md-dla-inference.md) | Model spaCy `pl_core_news_md` zamiast `lg` — inference zostaje na Lambdzie | przyjęta |
| [0016](0016-wyjasnienie-wyniku-shap.md) | Wyjaśnienie wyniku: top 5 cech wg SHAP w odpowiedzi API | przyjęta |

Lustro do przeglądania: Confluence, przestrzeń TAI-DETEKTOR → Architektura → Decyzje architektoniczne (ADR). **Źródłem prawdy jest to repozytorium.**

## Odstępstwa od `kontekst-projektu.md`
- Dodanie próbek nie uruchamia automatycznie retrainingu: próbki trafiają do stanu `pending`, retraining uruchamia admin lub próg N nowych próbek (do potwierdzenia przy projektowaniu pipeline'u).

## Backlog (must have)
- ~~Przenieść pipeline cech do `packages/features/` i podłączyć model XGBoost z S3 w Lambdzie~~ — gotowe (PR #9, #11).
- ~~Zmierzyć cold start z pełnym pipeline'em cech~~ — 3,6 s po bezczynności, timeout tylko przy pierwszym starcie nowego obrazu (spike, pomiar 2).
- Wdrożenie nowej wersji Lambdy bez przełączania aliasu → rozgrzanie i test dymny na wersji → przełączenie `champion`; `ignore_changes` na aliasie w Terraformie (ADR-0012, spike pomiar 2).
- Timeout Lambdy z powrotem do 30 s po wprowadzeniu rozgrzewania (dziś 120 s z czasu diagnozy).
- Członkowie zespołu: zaproszenia e-mailem w AWS Settings (IAM Identity Center niedostępne w new AWS experience) (ADR-0008).
- MFA na root (min. dwa urządzenia) zaraz po zakończeniu upgrade'u do planu Paid (ADR-0008).
- Bramka walidacji schematu cech w pipeline retrainingu (liczba, kolejność, typy, zakresy kolumn) przed porównaniem champion vs challenger.
- Włączenie ochrony gałęzi `main` (ADR-0009).
- Schematy kontraktów Java ↔ Python (parametry jobów Batch, wiadomości SQS, artefakty w S3) jako JSON Schema w repo + testy kontraktowe (ADR-0011).
- Pomiar pamięci Spring Boot + Postgres na t3.small; decyzja o t3.medium (ADR-0011).
- Limit zapytań per IP dla anonimowego endpointu oceny: Cloudflare vs AWS WAF (ADR-0011).
- ~~Bucket S3 na modele~~ — gotowe (`infra/terraform/envs/dev/artifacts.tf`). Zostaje: polityka retencji starych wersji Lambdy (ADR-0012).
- Reguła EventBridge (Batch → SQS `job-events`), DLQ z alarmem, schemat wiadomości postępu; idempotentny consumer w admin-api (ADR-0013).
- Lustro wag LLM w S3 + katalog modeli w Postgresie (źródło, wersja, SHA-256, licencja); pomiar czasu pobierania przy pierwszym uruchomieniu (ADR-0014).
- Pipeline generacji idempotentny i podzielny na porcje; dwie kolejki Batch (`spot`, `ondemand`) i przełącznik trybu awaryjnego w panelu admina (ADR-0010).
