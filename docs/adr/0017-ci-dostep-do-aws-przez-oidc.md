# ADR-0017: GitHub Actions — dostęp do AWS przez OIDC, bez stałych kluczy

- **Status:** przyjęta
- **Data:** 2026-11-22
- **Dotyczy:** ADR-0008 (konto AWS), ADR-0009 (repozytorium), ADR-0012 (promocja wersji Lambdy)

## Kontekst
Wdrożenia wykonujemy ręcznie z PowerShella: build i push obrazu, `terraform plan`/`apply` z `-var`, potem `scripts/deploy_inference.py`. Podczas ostatnich wdrożeń zdarzyły się:
- obraz zbudowany ze starym `$tag`,
- wygasłe tokeny w zmiennych `AWS_*`,
- ryzyko planu usuwającego Lambdę po zapomnieniu `-var`,
- `apply` z gałęzi zamiast z `main`.

Członkowie zespołu nie mają wygodnego dostępu do AWS (brak IAM Identity Center na tym koncie). CI (`.github/workflows/ci.yml`) uruchamia testy, ale nie ma dostępu do AWS. Repozytorium jest **publiczne**.

## Decyzja
1. GitHub Actions uwierzytelnia się w AWS przez **OIDC**. Przy każdym uruchomieniu workflowu GitHub wystawia krótkotrwały token, a STS wymienia go na tymczasowe poświadczenia roli. **Żadnych kluczy IAM w sekretach GitHuba.**
2. **Dwie role** w osobnym stacku `infra/terraform/ci/`:
   - **plan:** dla PR-ów z tego repo; `ReadOnlyAccess` + blokada stanu Terraformu. Służy do `terraform plan` jako komentarz w PR.
   - **deploy:** wyłącznie dla jobów w GitHub Environment `dev`, który jest ograniczony do `main` i wymaga ręcznego zatwierdzenia. Uprawnienia: `PowerUserAccess` + IAM tylko dla ról z prefiksem `ai-text-detector-*` + jawny `Deny` na zmianę ról CI i dostawcy OIDC.
3. **Stack `ci` stosuje wyłącznie człowiek.** CI nie może zmieniać własnych uprawnień. Nazwy ról CI (`github-actions-…`) leżą poza prefiksem, którym zarządza rola deploy.
4. ARN-y ról trzymamy jako *variables* GitHuba, nie *secrets*. Nie są tajne, bo dostęp kontroluje polityka zaufania.

## Uzasadnienie
- Brak stałego klucza oznacza, że nie ma czego wykraść ani rotować. To zgodne z AGENTS.md („bez sekretów i kluczy AWS w repo”).
- Warunek `sub` wiąże rolę z repozytorium i kontekstem: PR albo environment. PR-y z forków nie dostają tokenu OIDC, więc publiczne repo nie otwiera ról dla obcych.
- Ręczne zatwierdzenie w Environment `dev` daje „człowieka w pętli” przed każdą zmianą infrastruktury, tak jak dziś `plan` → przegląd → `apply`.

## Konsekwencje / trade-offy
- **Rola deploy jest silna.** `PowerUserAccess` to wszystko poza IAM. Pełne least privilege, czyli lista akcji per usługa, wymagałoby poprawek przy każdym nowym zasobie (Batch, SQS, EC2). Świadomy kompromis dla projektu studenckiego. W produkcji należy zawęzić uprawnienia do używanych usług i dodać permission boundary dla tworzonych ról.
- **Rola plan czyta całe konto,** łącznie ze stanem Terraformu i bucketem artefaktów. Każdy współpracownik z prawem push może w swoim PR zmienić workflow i użyć tej roli. Akceptowalne, bo współpracowników jest trzech. Przy większym zespole trzeba zawęzić odczyt.
- **Prefiks `ai-text-detector-*`** musi być zachowany dla wszystkich ról tworzonych przez Terraform w `envs/*`. Inaczej `apply` z CI skończy się błędem `AccessDenied`.
- Stack `ci` zmienia się rzadko i ręcznie. Każda zmiana uprawnień CI to PR i `apply` wykonany przez człowieka.

## Rozważone alternatywy
| Opcja | Powód odrzucenia |
|---|---|
| Klucze użytkownika IAM w sekretach GitHuba | Stały klucz w publicznym repo (sekret, ale zawsze ważny); rotacja; łamie AGENTS.md |
| Jedna rola dla planu i wdrożenia | PR mógłby wykonać `apply` bez zatwierdzenia |
| Role CI w `envs/dev` | CI mogłoby rozszerzyć własne uprawnienia (eskalacja) |
| Pełne least privilege dla roli deploy | Duży koszt utrzymania przy każdym nowym zasobie; wrócić przy wersji produkcyjnej |
| Brak CI dla AWS (ręczne wdrożenia) | Działa, ale powtarza błędy z ostatnich wdrożeń i wymaga dostępu do AWS dla każdego wdrażającego |
