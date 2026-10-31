# ADR-0011: Backend admina w Spring Boot + Spring Security; Python tylko w części ML

- **Status:** przyjęta
- **Data:** 2026-10-31
- **Zastępuje częściowo:** ADR-0005 — wybór FastAPI jako API admina (EC2, Docker Compose, Postgres, Caddy, SSM obowiązują)

## Kontekst
`kontekst-projektu.md` wymaga uwierzytelniania i rozdziału ról klient/admin. Diagram kontenerów (`docs/architecture/`) pokazał, że to nieustalone. Zespół zna Spring i czuje się w nim pewniej niż w Pythonie przy częściach administracyjnych. Panel admina nie liczy cech ani nie uruchamia modelu — cała logika ML jest w Lambdzie i workerach Batch.

## Decyzja
1. **Role:** klient korzysta **anonimowo** (bez logowania); jedyną rolą uwierzytelnianą jest **ADMIN**.
2. **Backend admina (`services/admin-api/`) w Spring Boot** zamiast FastAPI:
   - Spring Security: logowanie admina, hasło hashowane (Argon2 lub BCrypt) w Postgresie, sesja w ciasteczku `HttpOnly` + `Secure`, ochrona CSRF, limit prób logowania;
   - dostęp do Postgresa (np. Spring Data JPA + Flyway do migracji);
   - integracje z AWS przez AWS SDK for Java: Batch (`SubmitJob`, wybór kolejki `spot`/`ondemand` — ADR-0010), SQS (consumer logów — ADR-0006), Lambda (promocja = przełączenie aliasu — ADR-0004), S3.
3. **Python wyłącznie w części ML:** Lambda inference (`services/inference/`), workery (`pipelines/retraining/`), wspólny `packages/features/`.
4. **Java i Python nie wołają się nawzajem bezpośrednio.** Komunikują się przez usługi AWS: parametry joba Batch, artefakty w S3, wiadomości SQS, wersje i aliasy Lambdy. **Kontrakt = schematy tych komunikatów i artefaktów** (JSON Schema w repo), wersjonowane jak API.

## Uzasadnienie
- Kompetencje zespołu → szybsza i bezpieczniejsza implementacja; Spring Security to dojrzały standard.
- Panel admina nie potrzebuje Pythona; podział języków pokrywa się z granicą „administracja vs ML”.
- Odrzucony wariant pośredni (Spring tylko jako bramka logowania przed FastAPI): dwa serwisy do jednego zadania, dodatkowy przeskok sieciowy, dwa kontrakty API.

## Konsekwencje / trade-offy
- **Dwa języki w monorepo:** dwa toolchainy, dwa joby CI, dwa zestawy zależności do aktualizacji.
- **Pamięć:** JVM zajmuje kilkaset MB; na t3.small (2 GB) obok Postgresa jest ciasno. Plan: ograniczyć heap (`-Xmx`) i zmierzyć; prawdopodobnie przejście na **t3.medium (4 GB, ok. +$15/mies.)** — rewizja ADR-0005.
- **Kontrakty międzyjęzykowe** są jawnym punktem ryzyka: zmiana formatu wiadomości/artefaktu bez aktualizacji schematu psuje integrację po cichu → walidacja schematów po obu stronach i testy kontraktowe.
- **Anonimowy endpoint oceny tekstu** wymaga limitu zapytań per IP (throttling API Gateway jest per trasa, nie per klient) — do rozstrzygnięcia: Cloudflare przed API Gateway vs AWS WAF.
- Frontend (Cloudflare Pages) i backend admina na różnych hostach: CORS i ciasteczka sesyjne wymagają wspólnej domeny nadrzędnej (np. `app.` i `api.` w jednej domenie, `SameSite=Lax`).

## Rozważone alternatywy
| Opcja | Powód odrzucenia |
|---|---|
| FastAPI + własne logowanie (wszystko w Pythonie) | Jeden język i mniej utrzymania, ale zespół słabiej zna Pythona w tej roli |
| Spring Security jako bramka przed FastAPI | Dwa serwisy do jednego zadania, dodatkowy przeskok, dwa kontrakty |
| Amazon Cognito | Usługa zarządzana, ale nadmiarowa dla jednego konta admina; dodatkowa integracja i vendor lock-in |
