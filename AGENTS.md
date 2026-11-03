# AGENTS.md — System Detekcji Tekstów AI

Instrukcje dla agentów AI (Codex, Claude Code, Cursor) i dla ludzi pracujących w tym repo.

## Kontekst — przeczytaj przed pracą
- `docs/kontekst-projektu.md` — założenia projektu (**źródło prawdy**).
- `docs/adr/` — decyzje architektoniczne (ADR). Indeks, odstępstwa i backlog: `docs/adr/README.md`.
- `docs/architecture/` — diagramy architektury (Mermaid).
- `docs/design/` — briefy projektowe dla części w trakcie projektowania (np. pipeline retrainingu).
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

<!-- BEGIN AWS Agent Toolkit rules -->
# AWS Guidance for the new AWS experience

This user has signed up for the new AWS experience. This experience lets you sign into AWS using a social provider and requires the following additional context.

Where this guidance conflicts with the project's own instructions, the project's instructions take precedence.

## Context

### Terminology:

- Say "project" instead of "account" — a project contains an AWS account and settings for sharing with other collaborators
- Say "team member" instead of "IAM user" — users are invited by email, not created or federated in IAM
- Say "AWS Settings" when referring to management tasks at [settings.aws.com](https://settings.aws.com/) (project management, billing, team members, spend limits). Users view their actual AWS resources in the AWS Management Console.
- Say "selected Region" when referring to the user's Region — not "home Region"
- The user has a managed IAM experience. This includes a managed service control policies (SCP) and resource control policies (RCP) that govern the use of AWS. They will still need to use IAM to create policies to let services work with each other. If there are questions about the SCPs or RCPs, go to the documentation at https://docs.aws.amazon.com/accounts/latest/reference/scps-and-rcps-for-projects.html

### Constraints:

- All projects share a single AWS Region determined by the user's contact address. Resources cannot be created in other Regions
- When developing:
  - MUST create all Regional resources in the project's assigned Region
  - You CAN create AWS WAF and Cloudwatch Logs resources in us-east-1 when there are global resources (like a global WAF instance) that require a connection to dependencies in us-east-1. You should not use these for any other reason, because resources in the selected Region will provide lower cost (due to no cross-Region traffic), increased availability (due to no cross-Region traffic), and easier manageability (due to not needing to look in another Region). When you need to do an inventory of resources, you need to look in both the selected Region and us-east-1 for Cloudwatch Logs or WAF resources.
  - MUST NOT attempt to create Lambda, API Gateway, or other Regional resources in any other Region
  - MUST direct users to confirm their Region in AWS Settings > View all projects > Overview > Additional Info > Region. If the user cannot confirm their Region, check in ~/.aws/config
  - MUST NOT use Lambda@Edge — excluded from both Lambda and CloudFront
  - MUST NOT use CloudFormation StackSets — no multi-account or multi-Region deployments
  - MUST NOT attempt cross-Region actions — no cross-Region replication for DynamoDB/S3/RDS, no multi-Region KMS keys
  - MUST NOT use Route 53 cross-Region routing — geolocation, latency-based, and failover routing policies are not available
  - CloudFront is a global service and its actions ARE allowed in `us-east-1`. A user can create a CloudFront distribution pointing to their project-region Lambda function URL or API Gateway. However, Lambda and API Gateway themselves MUST NOT be created in `us-east-1` — they must be in the project Region.
  - Reduced availability in `eu-north-1` specifically: Amazon Rekognition, Amazon Textract, Amazon Personalize, AWS App Runner are not available in that Region.
- IAM permissions for human access are managed by AWS. Don't assign roles to team members unless absolutely necessary
- The user may have a spend limit if they are on the paid plan. The limit that pauses their project if it's exceeded. If resources suddenly become inaccessible, ask if they have a spend limit configured. Only project owners can modify a spend limit.
- When developing:
  - MUST ask about spend limit status if the user reports sudden "Access Denied" errors on operations that previously worked
  - MUST direct users to check spend status in AWS Settings > Billing
  - MUST check if a user has upgraded their account to the paid plan
  - MUST ask the user if they want to clean up the successfully created resources or keep them to reduce cost
- The user sets up billing, creates spend limits, and retrieves and pays invoices in AWS Settings. The user creates budgets and optimizes their costs in the AWS Billing and Cost Management console
- Not all AWS services are available. If a service isn't working, do the following:
  1. Run the command `aws freetier get-account-plan-state`
  2. If accountPlanType": "FREE", check the [Free Tier supported services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#supported-services-free-tier) next,
  3. If accountPlanType": "PAID", check the [Paid Tier supported services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#supported-services-paid-plan).
  4. If neither list shows the service, check the [Not supported for this experience list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#unsupported-services). The user will need to activate advanced features to access this service.
- Users can activate advanced AWS services and capabilities for their account.
- For any AWS task or question — building, configuring, migrating, debugging, or operating a service, writing SDK code, authoring CDK/CloudFormation, or answering how a service works — first call `aws___search_documentation` with topic `agent_skills` and load the matching skill with `aws___retrieve_skill`. Do this even when you believe you know the answer: skills carry current service behavior that your training may not. Prefer the skill's guidance over general knowledge. Skip it only for work that does not involve AWS.

### Help level

- help_level: HIGH (set by the user on 2026-10-30).

You CAN update this rule file to save a user's help_level.

Constraints for each level:

**LOW:**

- MUST follow all constraints in this context file
- MUST execute the user's request without modification
- MUST NOT ask clarifying questions unless the action would create a security vulnerability
- MUST NOT suggest alternatives or improvements

**MEDIUM:**

- MUST execute the user's request
- MAY ask up to two clarifying questions per task if the request has an ambiguity or a potential issue
- MUST NOT repeat a question or suggestion the user has already dismissed
- MUST NOT explain trade-offs or alternatives unless the user asks

**HIGH:**

- MUST explain what each step does and why before executing it
- MUST suggest alternatives when a better approach exists
- MUST flag best practices and explain trade-offs
- MUST still execute the user's choice if they disagree with a suggestion
<!-- END AWS Agent Toolkit rules -->
