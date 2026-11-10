# Trening modelu i eksport artefaktu

`train.py` — liczy cechy pakietem `detector_features` (schemat v2), trenuje XGBoost z najlepszymi hiperparametrami z `ai-text-recognition` (Optuna) i zapisuje **kompletny artefakt modelu** do wdrożenia na Lambdzie (ADR-0012).

Na razie uruchamiany ręcznie (lokalnie). Docelowo ten sam kod będzie krokiem treningu w AWS Batch (ADR-0003, ADR-0010) — zakres opisuje `docs/design/retraining-pipeline-brief.md`.

## Uruchomienie (PowerShell, z katalogu głównego repo)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r pipelines/retraining/requirements.txt

python pipelines/retraining/train.py `
  --data   "G:\...\ai-text-recognition\2025-smigiel\data\train\data.tsv" `
  --labels "G:\...\ai-text-recognition\2025-smigiel\data\train\labels.tsv" `
  --out    artifacts\model-v1
```
Szybki test na pierwszych 200 próbkach: dodaj `--limit 200 --out artifacts\test`.

Liczenie cech jest najdłuższym krokiem. Wynik trafia do `features.csv` w katalogu `--out` i jest używany ponownie przy kolejnym uruchomieniu z tym samym `--out` (np. po zmianie hiperparametrów). Przyspieszenie: `--n-process 4` (równoległe przetwarzanie spaCy).

## Artefakt (`--out`)
| Plik | Zawartość | Do S3? |
|---|---|---|
| `model.ubj` | model XGBoost (natywny format binarny) | tak |
| `feature_profile.json` | percentyle p1–p99, min/max, średnia per cecha na zbiorze treningowym — flaga OOD (ADR-0007) | tak |
| `metadata.json` | schemat i lista cech, wersje (spaCy, model językowy, xgboost, pakiet cech), hiperparametry, podział danych, metryki holdout, hashe danych wejściowych, commit | tak |
| `checksums.json` | SHA-256 trzech plików powyżej — Lambda weryfikuje je przy starcie (ADR-0012) | tak |
| `features.csv` | cache cech dla wszystkich próbek, z poprawnym nagłówkiem (38 cech + `label`) | **nie** |

Katalog `artifacts/` jest w `.gitignore` (AGENTS.md, zasada 3).

## Wysłanie artefaktu do S3
Każda wersja trafia do nowego prefiksu `models/<wersja>/` i nie jest później nadpisywana (ADR-0012). `features.csv` zostaje lokalnie.
```powershell
$bucket = terraform -chdir=infra\terraform\envs\dev output -raw artifacts_bucket_name
aws s3 ls "s3://$bucket/models/v1/"     # musi być pusto — nie nadpisujemy wersji
aws s3 cp artifacts\model-v1 "s3://$bucket/models/v1/" --recursive --exclude features.csv
aws s3 ls "s3://$bucket/models/v1/"     # oczekiwane 4 pliki
```

## Metryki
Stratyfikowany podział 80/20 (`--test-size`, `--seed`), metryki na holdout: accuracy, F1 macro, MCC, ROC-AUC — zapisane w `metadata.json`. Protokół porównania champion vs challenger (stały zbiór testowy, próg promocji) — do ustalenia w briefie retrainingu (pytania 18–22).
