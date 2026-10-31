# ADR-0013: Status jobów przez EventBridge i SQS (publisher–subscriber)

- **Status:** przyjęta
- **Data:** 2026-10-31

## Kontekst
Panel admina musi pokazywać stan uruchomień pipeline'u (ADR-0003, ADR-0010). Backend admina to Spring Boot (ADR-0011); workery to kontenery Pythona w AWS Batch. Bezpośredni callback workera do backendu wymagałby dostępu sieciowego workerów do EC2 i poświadczeń do API admina.

## Decyzja
1. **Stany jobów** (SUBMITTED → RUNNABLE → STARTING → RUNNING → SUCCEEDED / FAILED) bierzemy z natywnych zdarzeń **AWS Batch → Amazon EventBridge**. Reguła EventBridge (filtr: nasze kolejki Batch) przekazuje je do kolejki **SQS `job-events`**.
2. **Postęp biznesowy** (np. liczba wygenerowanych próbek w porcji, wynik ewaluacji champion vs challenger) workery publikują jako własne wiadomości do tej samej kolejki `job-events`, według schematu w repo (kontrakt Java ↔ Python — ADR-0011).
3. **admin-api** (Spring) konsumuje `job-events`, zapisuje stan i historię uruchomień w Postgresie. Przetwarzanie jest **idempotentne** (SQS dostarcza „co najmniej raz”; zdarzenia mogą przyjść w innej kolejności — rozstrzygamy po znaczniku czasu / numerze próby).
4. **Panel w przeglądarce** odpytuje admin-api co kilka sekund (must have). Server-Sent Events — nice to have.
5. Wiadomości, których nie da się przetworzyć, trafiają do **DLQ** (dead-letter queue) z alarmem w CloudWatch.

## Uzasadnienie
- Workery nie potrzebują dostępu sieciowego do EC2 ani poświadczeń API admina → mniejsza powierzchnia ataku.
- Zdarzenia czekają w kolejce, gdy EC2 jest niedostępne (restart, deploy) — nic nie ginie.
- Ten sam wzorzec co logi zapytań (ADR-0006): SQS + consumer w Springu.
- Stany z Batch są autorytatywne — także gdy worker padnie bez szansy na wysłanie komunikatu (np. przerwanie Spot, OOM).

## Konsekwencje / trade-offy
- Dodatkowe zasoby w IaC: reguła EventBridge, kolejka `job-events`, DLQ, uprawnienia (EventBridge → SQS, workery → `sqs:SendMessage`).
- Spójność ostateczna: panel pokazuje stan z opóźnieniem rzędu sekund.
- Schemat wiadomości postępu jest częścią kontraktów Java ↔ Python i wymaga testów kontraktowych.

## Rozważone alternatywy
| Opcja | Powód odrzucenia |
|---|---|
| Callback workera do admin-api (HTTP) | Workery potrzebują sieci do EC2 i poświadczeń; utrata statusu, gdy EC2 jest niedostępne lub worker padnie |
| Polling `DescribeJobs` przez admin-api | Działa, ale nie daje postępu biznesowego, obciąża API i opóźnia reakcję; zdarzenia są tańsze i dokładniejsze |
