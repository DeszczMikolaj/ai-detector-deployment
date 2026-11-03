# Środowisko `dev`

Infrastruktura projektu w regionie `eu-north-1`. Stan w buckecie z `../../bootstrap`.

Obecnie: **próbny przepływ inference** (ADR-0004) — ECR + Lambda z obrazem spaCy + API Gateway (HTTP API) z aliasem `champion`.

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
docker build --platform linux/amd64 --provenance=false -t "${repo}:$tag" services\inference
docker push "${repo}:$tag"
docker images "${repo}"             # rozmiar obrazu
```
`--provenance=false` jest wymagane — Lambda nie przyjmuje indeksów obrazów z atestacjami budowanymi domyślnie przez buildx.

### 3. Lambda + API Gateway
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

## Sprzątanie
Lambda i API Gateway nie kosztują nic bez ruchu. Aby usunąć tylko je: `terraform apply` bez `inference_image_tag`. Całość: `terraform destroy`.
