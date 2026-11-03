# Bootstrap — bucket na stan Terraform

Jednorazowo tworzy bucket S3, w którym wszystkie pozostałe katalogi `infra/terraform/` trzymają swój stan (z blokadą przez `use_lockfile`, bez DynamoDB). Region: `eu-north-1` (ADR-0008).

Co tworzy: 1 bucket S3 (wersjonowanie, szyfrowanie SSE-S3, blokada publicznego dostępu, wymuszony TLS, wygaszanie starych wersji stanu po 90 dniach). Koszt: groszowy (pliki stanu to kilobajty).

## Wymagania
- Terraform ≥ 1.10, AWS CLI v2.
- Zalogowane CLI: `aws login --region eu-north-1`, sprawdzenie: `aws sts get-caller-identity`.
- **Nigdy** stałe klucze dostępowe roota.

## Uruchomienie
```powershell
cd infra/terraform/bootstrap
terraform init
terraform fmt -check
terraform validate
terraform plan -out bootstrap.tfplan   # ← pokaż plan zespołowi / do review, zanim zrobisz apply (AGENTS.md, zasada 4)
terraform apply bootstrap.tfplan
```

Jeśli `terraform plan` zgłasza brak poświadczeń mimo działającego `aws sts get-caller-identity`, wyeksportuj krótkotrwałe poświadczenia do bieżącej sesji PowerShell:
```powershell
aws configure export-credentials --format powershell | Invoke-Expression
```
(wygasają po pewnym czasie — wtedy ponów `aws login` i eksport).

## Przeniesienie stanu bootstrapu do bucketa (krok 2)
1. Odkomentuj blok `backend "s3"` w `versions.tf` i wpisz nazwę z outputu `state_bucket_name`.
2. `terraform init -migrate-state` → potwierdź `yes`.
3. Usuń lokalne `terraform.tfstate*` (są już w buckecie i w `.gitignore`).

## Uwagi
- Bucket ma `prevent_destroy` — `terraform destroy` celowo się nie uda. Utrata stanu oznacza, że Terraform „zapomina” całą infrastrukturę.
- Plik `.terraform.lock.hcl` **commitujemy** (przypięte wersje providerów); `.terraform/`, `*.tfstate*` i `*.tfplan` — nie.
