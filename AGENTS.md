# AGENTS.md — System Detekcji Tekstów AI

Instrukcje dla agentów AI (Codex, Claude Code, Cursor) i dla ludzi pracujących w tym repo.

## Kontekst — przeczytaj przed pracą
- `docs/kontekst-projektu.md` — założenia projektu (**źródło prawdy**).
- `docs/adr/` — decyzje architektoniczne (ADR). Indeks, odstępstwa i backlog: `docs/adr/README.md`.
- `docs/architecture/` — diagramy architektury (Mermaid).
- Jeśli zadanie jest sprzeczne z `kontekst-projektu.md` lub z przyjętym ADR — **zatrzymaj się i zgłoś konflikt**, nie rozwiązuj go po cichu.

## O projekcie (skrót)
Projekt wdrożeniowy (studencki, ale ze standardami produkcyjnymi):
- **Inference:** klient wysyła tekst → klasyfikator (XGBoost na cechach stylometrycznych, spaCy `pl_core_news_lg`) zwraca ocenę AI vs człowiek. AWS Lambda (container image) za API Gateway.
- **Retraining (admin):** nowe próbki ludzkie → generacja próbek AI lokalnymi LLM-ami → trening → champion vs challenger → promocja tylko lepszego modelu. Efemeryczne zasoby (AWS Batch, workery CPU na Spot, GPU opcjonalne — ADR-0010).
- **Panel admina:** Spring Boot + Spring Security + Postgres na EC2 (Docker Compose) — ADR-0011. Python tylko w części ML (Lambda, workery, `packages/features/`).

## Struktura repo
```
docs/                     # kontekst + ADR
packages/features/        # preprocessing + ekstrakcja cech — JEDYNE źródło dla treningu i inference
services/inference/       # obraz Lambdy
services/admin-api/       # Spring Boot (Java): panel admina, auth, consumer SQS, zlecanie jobów Batch
pipelines/retraining/     # generacja, trening, ewaluacja, promocja
infra/terraform/          # IaC
.github/workflows/        # CI/CD
```

## Twarde zasady
1. **Cechy tylko z `packages/features/`.** Żadnej kopii logiki ekstrakcji w `services/` ani `pipelines/` (train/serve skew — ADR-0002).
2. **Zero sekretów w repo.** Żadnych kluczy AWS, haseł, tokenów, plików `.env`. CI łączy się z AWS przez OIDC.
3. **Żadnych danych ani modeli w gicie.** Zbiory, artefakty modeli i profile cech → S3.
4. **Nie twórz ani nie usuwaj zasobów AWS bez wyraźnej zgody człowieka.** Zmiany infrastruktury tylko przez Terraform w `infra/`, z `terraform plan` pokazanym przed `apply`.
5. **Bez surowego tekstu klientów w logach** (ADR-0006, RODO). Logujemy hash, długość, cechy, wynik.
6. **Wejście API zawsze z limitem długości tekstu** (ochrona przed DoS — ADR-0002).
7. **Determinizm:** stałe seedy w treningu i ekstrakcji cech (m.in. szum w NVG).
8. **Java ↔ Python tylko przez kontrakty.** Żadnych bezpośrednich wywołań między `services/admin-api/` a kodem Pythona; komunikacja przez Batch, SQS, S3 i aliasy Lambdy według schematów w repo (ADR-0011).

## Konwencje
- Dokumentacja i ADR: po polsku. Kod, nazwy, commity: po angielsku.
- Języki: Java (Spring Boot) w `services/admin-api/`; Python w `services/inference/`, `pipelines/`, `packages/`.
- Commity: Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`).
- Gałęzie: `feat/...`, `fix/...`, `docs/...`. **Nigdy nie pushuj bezpośrednio na `main`** — zmiany wyłącznie przez PR z co najmniej jednym review (ADR-0009).
- **Nowa decyzja architektoniczna = nowy plik ADR** (`docs/adr/NNNN-krotki-tytul.md`, format jak istniejące) + wpis w `docs/adr/README.md`. Nie edytuj treści przyjętego ADR — zastąp go nowym (status `zastąpiona przez ADR-XXXX`).

## Komendy
_Do uzupełnienia, gdy powstanie kod (instalacja zależności, testy, lint, build obrazu)._
