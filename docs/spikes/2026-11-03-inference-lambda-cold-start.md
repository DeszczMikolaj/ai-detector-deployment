# Spike: cold start Lambdy inference ze spaCy

- **Data:** 2026-11-03
- **Wykonał:** Mikołaj Deszcz (z pomocą Claude)
- **Dotyczy:** ADR-0004 (inference na Lambdzie), ADR-0002 (detektor, spaCy), ADR-0012 (model z S3)
- **Kod:** `services/inference/` (handler „tracer”), `infra/terraform/envs/dev/` (ECR, Lambda, API Gateway)

## Pytanie
Czy Lambda z obrazu kontenera z modelem spaCy mieści się w akceptowalnym czasie startu, zanim zbudujemy na tym ścieżkę inference? ADR-0004 zakładał cold start „kilka sekund”.

## Warunki testu
- Region `eu-north-1`, Lambda x86_64, **3008 MB** (maksimum dostępne na tym koncie), obraz `public.ecr.aws/lambda/python:3.12`.
- spaCy **3.8.13** (jak w treningu, `ai-text-recognition`), `spacy.load(..., disable=["ner", "textcat"])`.
- Handler „tracer”: ładowanie modelu w fazie init, przetworzenie tekstu (`NLP(text)`), proste statystyki — bez pipeline'u cech i XGBoosta.
- Punkt odniesienia: ten sam obraz uruchomiony lokalnie w Dockerze z emulatorem Lambdy, ograniczony do `--cpus 1.7 --memory 3g`.

## Wyniki

### Rozmiar obrazu
| Model | Rozmiar obrazu (lokalnie, rozpakowany) |
|---|---|
| `pl_core_news_lg` 3.8.0 | 2,39 GB |
| `pl_core_news_md` 3.8.0 | 1,28 GB |

### Cold start
| | Lokalnie (Docker, 1,7 CPU / 3 GB) | Lambda 3008 MB |
|---|---|---|
| `lg` — `spacy.load` | 1,2 s | **50,9 s** |
| `lg` — cały start | ~2,5 s | **> 60 s** (init 10 s timeout + ponowny init 30 s timeout; dopiero przy limicie 120 s udany) |
| `md` — import spaCy | 0,57 s | 0,63 s |
| `md` — `spacy.load` | 0,64 s | **3,2 s** |
| `md` — cały start (pierwszy dla nowego obrazu) | ~1,3 s | **~14,5 s** (init 10 s timeout + udane wywołanie 4,5 s) |

Logi Lambdy (`md`, pierwszy start nowego obrazu):
```
INIT_REPORT Init Duration: 9999.52 ms   Phase: init   Status: timeout
{"event": "init", "model": "pl_core_news_md", "import_seconds": 0.633, "load_seconds": 3.183}
REPORT Duration: 4452.17 ms   Memory Size: 3008 MB   Max Memory Used: 465 MB
```

### Warm start (przez API Gateway, z Polski)
| Wywołanie | Czas od strony klienta | Przetwarzanie w Lambdzie |
|---|---|---|
| 1 | 195 ms | 6,8 ms |
| 2 | 147 ms | 5,9 ms |
| 3 | 117 ms | 5,9 ms |

### Pamięć
`lg`: do ~1,25 GB; `md`: ~465 MB (z 3008 MB).

## Wnioski
1. **Procesor nie jest wąskim gardłem.** Ten sam obraz przy podobnym CPU ładuje `lg` lokalnie w 1,2 s, a w Lambdzie w 51 s.
2. **Wąskim gardłem jest ilość danych czytanych przy starcie.** Lambda podłącza obraz kontenera leniwie (fragmenty plików pobierane przy pierwszym odczycie). `lg` wymaga przeczytania kilkuset MB wektorów przy `spacy.load` — stąd dziesiątki sekund. `md` ma ~1,1 GB mniej danych w obrazie i ładuje się w 3,2 s.
3. **Lambda + `lg` jest nie do przyjęcia:** cold start > 60 s przekracza limit API Gateway (29 s) — każde zapytanie trafiające na nowe środowisko kończy się błędem 503.
4. **Lambda + `md` jest wykonalna:** warm 120–200 ms end-to-end; pierwszy cold start nowego obrazu ~14,5 s (mieści się w 29 s, ale jest wolny).
5. Zmiana modelu spaCy **zmienia cechy** (POS, morfologia, drzewo zależności liczone innym modelem) → klasyfikator musi być przetrenowany na tym samym modelu (ADR-0002, train/serve skew). To decyzja zespołu ML, nie infrastruktury.

## Ograniczenia konta wykryte przy okazji
- **Lambda: maks. 3008 MB pamięci** (`MemorySize ... less than or equal to 3008`) — limit nowego konta; nie da się dodać vCPU przez większą pamięć.
- **IAM Identity Center niedostępne** w „new AWS experience” — członków zespołu zaprasza się e-mailem w AWS Settings (aktualizacja otwartego punktu ADR-0008).
- **Docker na Windowsie + ECR:** token ECR jest za długi dla Menedżera poświadczeń Windows (`The stub received bad data`). Rozwiązanie: [Amazon ECR Credential Helper](https://github.com/awslabs/amazon-ecr-credential-helper) (`credHelpers` w `~/.docker/config.json`) — bez `docker login`.
- **AWS CLI** wymaga ustawionego regionu domyślnego (`aws configure set region eu-north-1`).

## Otwarte
- Czy **kolejne** cold starty `md` (obraz już w cache AWS) mieszczą się w 10 s za pierwszym podejściem (bez timeoutu fazy init)? Do zmierzenia: wymusić nowe środowisko (nowa wersja Lambdy) i powtórzyć wywołanie.
- Jakość klasyfikatora przetrenowanego na cechach z `md` vs `lg` — zadanie dla zespołu ML.
- Cold start po dodaniu prawdziwego pipeline'u cech (`packages/features`, networkx, ts2vg, XGBoost) i pobrania modelu z S3 (ADR-0012) — do zmierzenia ponownie.

## Stan zasobów po teście
Zostawione w `dev` (bez ruchu nie generują kosztu poza przechowywaniem obrazów w ECR): ECR `ai-text-detector/inference` (obrazy `44191ce` = `lg`, `accaa0c-md` = `md`), Lambda `ai-text-detector-inference` (alias `champion` → wersja z `md`, timeout 120 s), HTTP API z trasą `POST /evaluate`.
