# Środowisko `dev`

Infrastruktura projektu w regionie `eu-north-1`. Stan w buckecie z `../../bootstrap`.

Obecnie:
- **inference** (ADR-0004, ADR-0012) — ECR + Lambda (spaCy + XGBoost, model championa z S3 `models/<inference_model_version>/`) + API Gateway (HTTP API) z aliasem `champion`; kontrakt API: `services/inference/README.md`,
- **bucket artefaktów ML** (`artifacts.tf`, ADR-0012, ADR-0014) — modele, zbiory danych, wagi LLM, backupy.

## Zmienne przy każdym `plan` (ważne)
Terraform nie pamięta wartości `-var` z poprzednich uruchomień. Dopóki tag obrazu nie przychodzi z CI, **każdy** `plan` musi podawać aktualne wartości:
```powershell
terraform plan -var "inference_image_tag=<obecny tag>" -out dev.tfplan
```
Bez tego `inference_image_tag` wraca do `null`, a plan **usuwa** Lambdę i API Gateway. Obecny tag: `aws lambda get-function-configuration --function-name ai-text-detector-inference --qualifier champion --query Code.ImageUri`.
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

### 3. Lambda + API Gateway (nowa wersja)
Model championa musi już leżeć w S3 pod `models/<inference_model_version>/` (domyślnie `v1`; wysyłka: `pipelines/retraining/README.md`).
```powershell
cd infra\terraform\envs\dev
terraform plan -var "inference_image_tag=$tag" -out dev.tfplan
terraform apply dev.tfplan
terraform output inference_version          # wersja, którą widzą klienci (alias champion)
terraform output inference_latest_version   # nowa wersja — jeszcze bez ruchu
```
**`apply` nie przełącza klientów na nową wersję.** Każda zmiana Lambdy publikuje nową, niezmienną wersję, ale alias `champion` ma w Terraformie `ignore_changes` — przy pierwszym utworzeniu wskazuje najnowszą wersję, później przełącza go wyłącznie krok 4 (docelowo także admin-api przy promocji modelu, ADR-0012). Źródłem prawdy o wersji championa jest AWS.

### 4. Rozgrzanie, test dymny i przełączenie aliasu
Pierwsze uruchomienia świeżo wdrożonego obrazu doczytują go z ECR i mogą przekroczyć limit fazy init (10 s) — gdyby trafili na nie klienci, dostaliby **503** (spike `docs/spikes/2026-11-03-inference-lambda-cold-start.md`, pomiar 2). Dlatego nową wersję wywołujemy najpierw bezpośrednio, z pominięciem API Gateway:
```powershell
cd ..\..\..\..
uv pip install "boto3[crt]"   # jednorazowo; [crt] jest potrzebne do logowania przez `aws login`
python scripts/deploy_inference.py --expect-model-version v1
```
Skrypt:
1. rozgrzewa najnowszą wersję (do 6 prób, aż odpowie `200`),
2. robi test dymny — 3 oceny tekstu (etykieta, prawdopodobieństwo, 5 cech w `explanation`, wersja modelu) i odrzucenie pustego tekstu (`400`),
3. przełącza alias `champion` (z `RevisionId` — nie nadpisze równoległej zmiany).

Przy błędzie alias zostaje bez zmian. Opcje: `--version N` (konkretna wersja, także **rollback**: skrypt na końcu wypisuje komendę powrotu), `--no-switch` (tylko test).

### 5. Sprawdzenie przez API
```powershell
cd infra\terraform\envs\dev
$url = terraform output -raw evaluate_url
$body = '{"text": "Wczoraj wieczorem poszedłem do kina. Film był długi, ale bardzo ciekawy i dobrze zagrany."}'
Invoke-RestMethod -Method Post -Uri $url -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($body)) | ConvertTo-Json -Depth 5
```
Szczegóły z CloudWatch (linie `REPORT`: `Init Duration`, `Duration`, `Max Memory Used`; logi `evaluate`: `processing_ms`, `shap_ms`):
```powershell
aws logs tail /aws/lambda/ai-text-detector-inference --since 15m --format short | Select-String "REPORT|shap_ms"
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
