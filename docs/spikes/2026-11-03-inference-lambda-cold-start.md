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

## Otwarte (stan na 2026-11-03)
- ~~Czy **kolejne** cold starty `md` (obraz już w cache AWS) mieszczą się w 10 s?~~ — tak, patrz „Pomiar 2”.
- ~~Jakość klasyfikatora przetrenowanego na cechach z `md` vs `lg`~~ — zespół ML przetrenował na `md` z zadowalającym wynikiem (ADR-0015 przyjęta).
- ~~Cold start po dodaniu pipeline'u cech i modelu z S3~~ — patrz „Pomiar 2”.

## Pomiar 2 (2026-11-11): pełny pipeline — cechy + XGBoost z S3
Obraz `0ef5503` (PR #11): `detector_features` (networkx, ts2vg), `xgboost-cpu` 3.4.1, spaCy `md`; model `v1` pobierany z `s3://…/models/v1/` i weryfikowany w fazie init (ADR-0012). Lambda 3008 MB, `eu-north-1`.

| Faza init | Pierwszy start po wdrożeniu obrazu | Cold start po ~1 h bezczynności | Lokalnie (Windows, venv) |
|---|---|---|---|
| import bibliotek | 21,8 s | **1,4 s** | 3,5 s |
| ładowanie spaCy `md` | 11,1 s | **1,3 s** | 0,7 s |
| model z S3 + weryfikacja SHA-256/schematu | 1,1 s | **0,8 s** | 0,06 s (dysk lokalny) |
| **Init Duration** | **> 10 s → timeout**, ponowny init w wywołaniu: 34,4 s | **3,6 s** | 4,3 s |
| przetwarzanie zapytania (cechy + predykcja) | 351 ms | 20 ms | 11 ms |

- **Warm:** przetwarzanie 15,8–16,7 ms (3 wywołania).
- **Pamięć:** maks. 625 MB z 3008 MB.
- **Pierwszy start po wdrożeniu** przekroczył limit fazy init (10 s); ponowny init trwał 34 s > 29 s limitu API Gateway → **klient dostał 503**. Drugie równoległe środowisko zmieściło się w 9,7 s.

Logi (cold start po bezczynności):
```
{"event": "init", "model_version": "v1", ..., "import_seconds": 1.434, "spacy_load_seconds": 1.261, "model_load_seconds": 0.763}
REPORT Duration: 21.78 ms   Billed Duration: 3658 ms   Memory Size: 3008 MB   Max Memory Used: 621 MB   Init Duration: 3635.40 ms
```

### Wnioski (pomiar 2)
1. **Kod i model nie są problemem** — cold start po bezczynności 3,6 s, warm ~16 ms. Pobranie i weryfikacja modelu z S3 to < 1 s (ADR-0012 zakładał „ułamek sekundy”).
2. **Problemem jest tylko pierwszy start świeżo wdrożonego obrazu** (leniwe doczytywanie warstw z ECR — ten sam mechanizm co w pomiarze 1). Różnica 10× wynika wyłącznie z tego, czy Lambda ma obraz w cache.
3. **Provisioned concurrency ani cykliczny ping nie są potrzebne.** Wystarczy, że klienci nie trafiają na nową wersję, zanim zostanie rozgrzana.

### Rekomendacja: rozgrzanie nowej wersji przed przełączeniem aliasu
- **Teraz (dev, brak ruchu klientów):** po każdym `apply` z nowym obrazem kilka wywołań testowych (`infra/terraform/envs/dev/README.md`, krok 5).
- **Docelowo:** wdrożenie publikuje nową wersję Lambdy **bez** przełączania aliasu → rozgrzanie i test dymny na ARN wersji → przełączenie `champion`. To przepływ promocji z ADR-0012 (pkt 4); wymaga `ignore_changes = [function_version]` na aliasie w Terraformie (TODO w `inference.tf`). Nie wymaga nowego ADR.

### Zauważone przy okazji
Krótki tekst napisany przez człowieka (86 znaków) dostał `ai` (0,60). Do sprawdzenia przez zespół ML: rozkład długości tekstów w zbiorze treningowym i ewentualna minimalna długość wejścia API.

## Stan zasobów po teście
**Po pomiarze 2 (2026-11-11):** alias `champion` → wersja z obrazem `0ef5503` i `MODEL_URI=s3://…/models/v1/`; timeout nadal 120 s; bucket artefaktów `ai-text-detector-artifacts-366366122547-eu-north-1`.

Po pomiarze 1 (2026-11-03): zostawione w `dev` (bez ruchu nie generują kosztu poza przechowywaniem obrazów w ECR): ECR `ai-text-detector/inference` (obrazy `44191ce` = `lg`, `accaa0c-md` = `md`), Lambda `ai-text-detector-inference` (alias `champion` → wersja z `md`, timeout 120 s), HTTP API z trasą `POST /evaluate`.
