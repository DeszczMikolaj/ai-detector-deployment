# ADR-0012: Model championa ładowany z S3; obraz Lambdy zawiera tylko kod i spaCy

- **Status:** przyjęta
- **Data:** 2026-10-31
- **Zastępuje częściowo:** ADR-0004 — „model zapieczony w obrazie” (Lambda za API Gateway, alias `champion`, cold starty i reszta ADR-0004 obowiązują)

## Kontekst
ADR-0004 zakładał, że model XGBoost jest zapieczony w obrazie Lambdy. Wtedy każda promocja wymaga zbudowania nowego obrazu w CI. Pipeline retrainingu działa w AWS Batch, a decyzję o promocji wykonuje admin-api (ADR-0011) — żaden z nich nie powinien zależeć od uruchomienia GitHub Actions.

## Decyzja
1. **Obraz Lambdy** zawiera: Python, zależności, model spaCy `pl_core_news_lg`, kod `services/inference/` i `packages/features/`. **Nie zawiera** modelu XGBoost ani profilu cech.
2. **Artefakty modelu** (plik modelu, profil cech dla OOD — ADR-0007, metadane: wersja schematu cech, wersja spaCy, metryki ewaluacji, hash pliku) leżą w S3 pod niezmiennym prefiksem wersji, np. `s3://…/models/v7/`. Prefiksy są **tylko do zapisu raz** (bez nadpisywania; wersjonowanie bucketa włączone).
3. **Wersja Lambdy** = obraz + zmienna środowiskowa `MODEL_URI` wskazująca prefiks wersji modelu. Lambda w fazie init pobiera artefakty z S3, **weryfikuje hash** i zgodność wersji schematu cech z kodem `packages/features/`; przy niezgodności init kończy się błędem (wersja nie przyjmie ruchu).
4. **Promocja** (admin-api): opublikowanie nowej wersji Lambdy z nowym `MODEL_URI` → test dymny na tej wersji → przełączenie aliasu `champion`. **Rollback** = przełączenie aliasu na poprzednią wersję.
5. **Nowy obraz** budujemy tylko przy zmianie kodu lub zależności (CI), nie przy zmianie modelu.

## Uzasadnienie
- **Promujemy dokładnie ten plik, który wygrał porównanie champion vs challenger** — bez przebudowy obrazu, więc bez ryzyka, że CI zapakuje inny artefakt niż oceniony.
- Promocja trwa sekundy i nie zależy od GitHub Actions.
- Rozdział cykli życia: kod (CI, PR, review) vs model (pipeline retrainingu, metryki).

## Konsekwencje / trade-offy
- Cold start dłuższy o pobranie artefaktów z S3 (kilka MB — rząd ułamka sekundy; do zmierzenia w spike'u Lambdy).
- Rola IAM Lambdy potrzebuje odczytu z prefiksu modeli w S3 (tylko odczyt, tylko ten prefiks).
- Kompatybilność model ↔ kod staje się jawnym kontraktem: zmiana `packages/features/` zmieniająca cechy wymaga nowej wersji schematu cech i nowego modelu (powiązane z bramką walidacji schematu w backlogu).
- Starych wersji Lambdy i artefaktów nie usuwamy automatycznie — potrzebna polityka retencji (np. ostatnie N wersji).

## Rozważone alternatywy
| Opcja | Powód odrzucenia |
|---|---|
| Model w obrazie (ADR-0004) | Promocja wymaga CI i przebudowy; ryzyko rozjazdu ocenionego i serwowanego artefaktu |
| Lambda czyta „najnowszy” model z S3 bez wersji | Brak atomowej promocji i rollbacku; różne środowiska mogłyby serwować różne modele |
