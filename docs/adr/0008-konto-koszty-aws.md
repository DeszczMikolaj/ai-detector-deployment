# ADR-0008: Konto i koszty AWS

- **Status:** rekomendacja
- **Data:** 2026-10-29

## Decyzja
Jedno konto zespołowe w planie Paid (plan Free zamyka konto po 6 miesiącach lub wyczerpaniu kredytów). AWS Budgets z alertami, MFA na root, IAM Identity Center dla członków zespołu, IaC (Terraform) umożliwiające szybkie zburzenie środowiska.

## Pułapki kosztowe do unikania
NAT Gateway, EKS, ALB, zapomniane instancje GPU, wolumeny EBS i snapshoty.

## Otwarte
- Konto założone w „new AWS experience” (project, logowanie społecznościowe) — do sprawdzenia, czy pozwala dodać członków zespołu i ustawić Budgets zgodnie z tą decyzją.
- Region projektu: `eu-north-1` — sprawdzić dostępność typów instancji G przed wnioskiem o quotę GPU (ADR-0001).
