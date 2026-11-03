# ADR-0008: Konto, region i koszty AWS

- **Status:** przyjęta
- **Data:** 2026-10-29 (rekomendacja), 2026-11-03 (przyjęta: plan Paid, region `eu-north-1`)

## Decyzja
1. **Jedno konto zespołowe w planie Paid.** Plan Free zamyka konto po 6 miesiącach lub po wyczerpaniu kredytów (razem z zasobami i danymi) i blokuje część usług. Upgrade jest nieodwracalny; niewykorzystane kredyty nadal pokrywają rachunki do wygaśnięcia.
2. **Region projektu: `eu-north-1` (Sztokholm).** Wszystkie zasoby tworzymy w tym regionie, chyba że usługa jest globalna.
3. **Bezpieczeństwo konta:** MFA na root (minimum dwa urządzenia), root tylko do rzadkich operacji administracyjnych; członkowie zespołu pracują na własnych tożsamościach z ograniczonymi uprawnieniami.
4. **Kontrola kosztów:** AWS Budgets z alertami (kilka progów, koszt rzeczywisty i prognozowany, powiadomienia do więcej niż jednej osoby); infrastruktura jako kod (Terraform) umożliwiająca szybkie zburzenie środowiska.

## Uzasadnienie regionu
- Wnioski o quoty (Standard On-Demand i Spot, G and VT) złożono i zatwierdzono w `eu-north-1` — przeniesienie regionu oznaczałoby ponowne wnioski i oczekiwanie.
- Wszystkie usługi z ADR-0004, 0010, 0012, 0013 (Lambda z obrazem kontenera, API Gateway, Batch, EventBridge, SQS, ECR, S3) są dostępne w `eu-north-1`; ceny zwykle nieco niższe niż w `eu-central-1`.
- Trade-off: mniejsza pula pojemności Spot i węższy wybór typów instancji niż we Frankfurcie → możliwe częstsze przerwania Spot. Łagodzenie: kilka typów instancji w compute environment Batch, kolejka `ondemand` (ADR-0010).

Wzmianki o `eu-central-1` w ADR-0010 (sekcja o quotach) są nieaktualne — obowiązuje region z tego ADR.

## Pułapki kosztowe do unikania
NAT Gateway, EKS, ALB, zapomniane instancje (zwłaszcza GPU), wolumeny EBS i snapshoty, publiczne adresy IPv4.

## Stan wdrożenia (2026-11-03)
- [x] Alert budżetowy założony.
- [x] Quoty w `eu-north-1` zatwierdzone.
- [ ] Upgrade do planu Paid — w trakcie przetwarzania po stronie AWS.
- [ ] MFA na root — po zakończeniu upgrade'u (wcześniej niedostępne w konsoli).
- [ ] Tożsamości dla członków zespołu.

## Otwarte
- Konto założone w „new AWS experience” (projekty, logowanie społecznościowe; inne menu konta niż w klasycznej konsoli) — do sprawdzenia, jak dodaje się członków zespołu i czy dostępne jest IAM Identity Center.
