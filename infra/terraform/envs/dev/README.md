# Środowisko `dev`

Infrastruktura projektu w regionie `eu-north-1`. Stan w buckecie z `../../bootstrap`.

Obecnie:
- **inference** (ADR-0004, ADR-0012) — ECR + Lambda (spaCy + XGBoost, model championa z S3 `models/<inference_model_version>/`) + API Gateway (HTTP API) z aliasem `champion`; kontrakt API: `services/inference/README.md`,
- **bucket artefaktów ML** (`artifacts.tf`, ADR-0012, ADR-0014) — modele, zbiory danych, wagi LLM, backupy.

## Zmienne przy każdym `plan` (ważne)
Terraform nie pamięta wartości `-var` z poprzednich uruchomień. Dopóki tag obrazu nie przychodzi z CI, **każdy** `plan` musi podawać aktualne wartości:
```powershell
terraform plan -var "inference_image_tag=<obecny tag>" -var "inference_timeout_s=<obecny timeout>" -out dev.tfplan
```
Bez nich `inference_image_tag` wraca do `null`, a plan **usuwa** Lambdę i API Gateway (oraz cofa timeout do domyślnych 30 s). Obecne wartości: `aws lambda get-function-configuration --function-name ai-text-detector-inference --query "[Timeout, Code.ImageUri]"`.
Zasada: przy zmianie niezwiązanej z inference oczekujemy `0 to change, 0 to destroy`; inaczej nie robimy `apply`.

## Kolejność pierwszego wdrożenia (PowerShell, z katalogu głównego repo)

### 1. Repozytorium ECR
```powershell
cd infra\terraform\envs\dev
terraform init
terraform plan -out dev.tfplan      # oczekiwane: 3 zasoby ECR (repo, lifecycle, policy)
terraform apply dev.tfplan
$repo = terraform output -raw inference_repository_url
cd ..\..\..\..
```

### 2. Obraz → ECR
```powershell
$region = "eu-north-1"
$registry = $repo.Split("/")[0]
aws ecr get-login-password --region $region | docker login --username AWS --password-stdin $registry
$tag = git rev-parse --short HEAD
docker build --platform linux/amd64 --provenance=false -f services\inference\Dockerfile -t "${repo}:$tag" .
docker push "${repo}:$tag"
docker images "${repo}"             # rozmiar obrazu
```
`--provenance=false` jest wymagane — Lambda nie przyjmuje indeksów obrazów z atestacjami budowanymi domyślnie przez buildx.
Kontekst budowania to katalog główny repo (obraz potrzebuje `packages/features`); co do niego trafia, określa `services/inference/Dockerfile.dockerignore`.

### 3. Lambda + API Gateway
Model championa musi już leżeć w S3 pod `models/<inference_model_version>/` (domyślnie `v1`; wysyłka: `pipelines/retraining/README.md`).
```powershell
cd infra\terraform\envs\dev
terraform plan -var "inference_image_tag=$tag" -out dev.tfplan
terraform apply dev.tfplan
$url = terraform output -raw evaluate_url
```

### 4. Pomiar
```powershell
$body = '{"text": "Wczoraj wieczorem poszedłem do kina. Film był długi, ale bardzo ciekawy i dobrze zagrany."}'
Invoke-RestMethod -Method Post -Uri $url -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($body))
```
Pierwsze wywołanie = cold start (`timing.cold_start = true`, `timing.init_seconds`). Kolejne = warm.
Szczegóły z CloudWatch (linie `REPORT`: `Init Duration`, `Duration`, `Max Memory Used`):
```powershell
aws logs tail /aws/lambda/ai-text-detector-inference --since 15m --format short | Select-String "REPORT"
```

## Bucket artefaktów
Nazwa: `terraform output -raw artifacts_bucket_name` (`ai-text-detector-artifacts-<konto>-eu-north-1`).

Konwencja prefiksów (nie wymuszana przez S3):

| Prefiks | Zawartość | Zasada |
|---|---|---|
| `models/<wersja>/` | `model.ubj`, `feature_profile.json`, `metadata.json`, `checksums.json` | zapis raz, bez nadpisywania |
| `datasets/<nazwa>/<wersja>/` | `data.tsv`, `labels.tsv`, `manifest.json` | zapis raz; najpierw sprawdzić licencję zbioru |
| `llm/<rodzina>/<wersja>/` | wagi lokalnych LLM (ADR-0014) | zapis raz |
| `backups/` | `pg_dump` bazy (ADR-0005) | — |

Zabezpieczenia: brak dostępu publicznego, wersjonowanie (poprzednie wersje znikają po 90 dniach — `artifacts_noncurrent_retention_days`), szyfrowanie SSE-S3, tylko HTTPS, `prevent_destroy`.

## Sprzątanie
Lambda i API Gateway nie kosztują nic bez ruchu. Aby usunąć tylko je: `terraform apply` bez `inference_image_tag`.
`terraform destroy` zatrzyma się na buckecie artefaktów (`prevent_destroy`) — to celowe; jego usunięcie wymaga świadomej zmiany kodu i opróżnienia bucketa razem z wersjami.
