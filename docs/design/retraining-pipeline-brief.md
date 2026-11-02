# Brief projektowy: pipeline retrainingu

- **Status:** otwarty — czeka na odpowiedzi zespołu
- **Zlecający:** Mikołaj Deszcz
- **Wykonawcy:** _do uzupełnienia_
- **Termin:** _do uzupełnienia_
- **Data:** 2026-11-02

## Po co ten dokument
Zaprojektować część administracyjną systemu: od dodania próbek ludzkich do decyzji „promujemy nowy model albo zostaje stary” (`kontekst-projektu.md`, sekcje 2 i 3). Infrastruktura jest już ustalona (ADR-y poniżej). Ten brief zbiera **pytania, na które projekt musi odpowiedzieć** — bez tych odpowiedzi pipeline da się zbudować, ale nie da się obronić, że działa poprawnie.

## Czego oczekujemy na wyjściu
1. **Odpowiedź na każde pytanie** w formacie: _decyzja → uzasadnienie → odrzucona alternatywa_. Dopuszczalne „nie wiemy — potrzebny spike”, ale wtedy z właścicielem i terminem.
2. **Propozycje ADR** (od ADR-0015 w górę) dla decyzji, które wiążą resztę systemu — w szczególności: trigger pipeline'u, strategia puli treningowej, protokół ewaluacji i reguła promocji.
3. **Diagram sekwencji** retrainingu w Mermaid w `docs/architecture/` (od kliknięcia admina do przełączenia aliasu lub odrzucenia challengera).
4. **Kontrakty** (JSON Schema) dla danych przekraczających granicę Java ↔ Python: parametry joba, wiadomości postępu, manifest datasetu, raport ewaluacji.

Dyskusja: komentarze w Confluence przy tym dokumencie. Decyzje: ADR-y w repo przez PR.

## Ustalenia wiążące (nie projektujemy od nowa)
| ADR | Co z tego wynika dla pipeline'u |
|---|---|
| [0001](../adr/0001-generator-lokalne-llm.md), [0014](../adr/0014-lustro-wag-llm-s3.md) | Generatory to lokalne LLM-y z lustra w S3, przypięte wersje; brak zewnętrznych API |
| [0002](../adr/0002-detektor-xgboost-cpu.md) | Detektor: XGBoost na ~37 cechach; ekstrakcja **tylko** z `packages/features/` |
| [0003](../adr/0003-efemeryczny-pipeline.md), [0010](../adr/0010-workery-cpu-spot.md) | AWS Batch, workery CPU na Spot, porcje ~25 próbek, idempotentny zapis do S3, kolejka `ondemand` jako tryb awaryjny |
| [0007](../adr/0007-drift-ood.md) | Każdy model ma profil cech (percentyle) zapisany razem z nim |
| [0011](../adr/0011-backend-admina-spring.md) | Orkiestracja i panel w Spring Boot; Java ↔ Python tylko przez Batch/SQS/S3 i schematy |
| [0012](../adr/0012-model-championa-z-s3.md) | Artefakty modelu w S3 pod niezmiennym prefiksem; promocja = nowa wersja Lambdy + alias |
| [0013](../adr/0013-status-jobow-eventbridge-sqs.md) | Status i postęp przez EventBridge + SQS `job-events` |

Znane ograniczenia: generacja ~2 min/próbkę na CPU (spike z ADR-0010); docelowo setki próbek na uruchomienie.

---

## Pytania

### A. Wejście: próbki ludzkie i uruchomienie
1. **Co uruchamia pipeline?** Admin ręcznie, automatycznie po N próbkach w stanie `pending`, harmonogram — czy kombinacja? Jeśli próg, to jakie N i dlaczego? _(To jest odstępstwo od `kontekst-projektu.md`, które trzeba zatwierdzić albo odrzucić.)_
2. **Kryteria walidacji próbki ludzkiej:** min./maks. długość, język polski (jak sprawdzany?), kodowanie, duplikaty dokładne i prawie-duplikaty (jak wykrywane?), czy tekst nie jest przypadkiem wygenerowany przez AI. Co dzieje się z odrzuconą próbką i czy admin widzi powód?
3. **Jakie metadane musi mieć próbka ludzka?** Np. domena/gatunek (esej, wiadomość, artykuł), źródło, data, podstawa prawna/licencja. Które pola są obowiązkowe?
4. **Format i limity dodawania:** pojedynczo w panelu, upload pliku (CSV/JSONL)? Maks. rozmiar paczki?
5. **Dane osobowe:** czy próbki ludzkie mogą zawierać dane osobowe? Jeśli tak — jak je wykrywamy/anonimizujemy i jak długo przechowujemy (RODO)?

### B. Generacja próbek AI
6. **Jak z próbki ludzkiej powstaje prompt?** Temat, streszczenie, pierwsze zdanie, styl/gatunek? Czy szablony promptów są wersjonowane i zapisywane przy próbce?
7. **Ile próbek AI na jedną ludzką** i **z których generatorów** (wszystkie z lustra, losowo, rotacyjnie)? Czy chcemy zrównoważyć udział generatorów w zbiorze?
8. **Parametry generacji:** temperatura, top-p, seed, docelowa długość. ⚠️ Długość tekstu to cecha modelu (`Token_Count`, `Char_Length`) — jeśli teksty AI będą systematycznie krótsze/dłuższe od ludzkich, detektor nauczy się rozpoznawać długość, nie styl. **Jak dopasowujemy długość?**
9. **Kontrola jakości wygenerowanego tekstu:** co odrzucamy (pusty, ucięty, w innym języku, pętle powtórzeń, meta-teksty typu „Jako model językowy…”)? Ile prób ponowienia na próbkę?
10. **Częściowy sukces:** jeśli część porcji się nie uda — jaki minimalny odsetek udanych próbek pozwala kontynuować trening?

### C. Pula treningowa (kwestia otwarta w `kontekst-projektu.md`, sekcja 3)
11. **Maksymalny rozmiar puli** i co się dzieje po jego przekroczeniu: retencja (najstarsze wypadają), deduplikacja, selekcja reprezentatywna (np. klastrowanie po cechach), selekcja najbardziej informatywnych próbek?
12. **Balans:** czy pula ma być zbalansowana 50/50 człowiek/AI? Per domena? Per generator?
13. **Zapominanie:** czy próbki ze starszych generatorów zostają, żeby model nadal je wykrywał? Kto i jak decyduje o ich usunięciu?
14. **Pochodzenie modelu:** jak zapisujemy, z czego powstał każdy model (manifest: ID i hashe próbek, wersja kodu i konfiguracji, generatory)? Czy wymagamy możliwości ponownego wytrenowania starych modeli — a jeśli tak, to których (np. tylko obecny champion i jego poprzednik) i jak godzimy to z retencją puli (pytanie 11)?

### D. Trening
15. **Podział train / validation / test:** losowy, stratyfikowany, czy grupowy? ⚠️ Próbka ludzka i wygenerowane z niej próbki AI muszą trafić **do tego samego** podzbioru — inaczej wyciek informacji i zawyżone wyniki.
16. **Hiperparametry:** stałe czy strojone przy każdym treningu (np. Optuna)? Jaki budżet czasu? Seed?
17. **Bramka schematu cech** (backlog): co dokładnie sprawdza przed treningiem — liczba i kolejność kolumn, typy, zakresy, odsetek NaN/zer?

### E. Ewaluacja champion vs challenger (kwestia otwarta w `kontekst-projektu.md`)
18. **Na czym porównujemy?** Czy istnieje **stały zbiór testowy** (golden set), niezmienny między wersjami, z etykietami? Kto go tworzy, ile próbek, jak często i jak go aktualizujemy, żeby porównania były uczciwe? Czy nowe próbki z bieżącego uruchomienia też wchodzą do oceny?
19. **Metryka główna:** F1, ROC-AUC, PR-AUC, czy recall AI przy ograniczonym odsetku fałszywych alarmów? ⚠️ Fałszywe oskarżenie człowieka o użycie AI ma inny koszt niż przepuszczenie tekstu AI — **który błąd jest dla nas gorszy i jaki maks. FPR akceptujemy?**
20. **Warunki „nie gorzej niż”:** czy challenger musi nie pogorszyć wyników per domena i per generator (żeby średnia nie ukryła regresji w jednej grupie)?
21. **Reguła promocji:** minimalna poprawa (np. o ile punktów procentowych) i jak sprawdzamy, że to nie szum (przedziały ufności bootstrap, test McNemara)?
22. **Kalibracja:** API zwraca prawdopodobieństwo — czy wymagamy kalibracji (np. reliability diagram, ECE) jako warunku promocji?
23. **Warunki niefunkcjonalne:** maks. rozmiar modelu i czas predykcji (cold start Lambdy — ADR-0004/0012).
24. **Promocja automatyczna czy z zatwierdzeniem admina?** Co admin widzi przed kliknięciem „promuj”?
25. **Raport ewaluacji:** jakie elementy (metryki, macierz pomyłek, wyniki per grupa, SHAP top-cechy), gdzie zapisany (S3 + Postgres), jak prezentowany w panelu?

### F. Operacje i przypadki brzegowe
26. **Challenger przegrywa:** co z jego artefaktami i z nowymi próbkami — zostają w puli na następny raz?
27. **Równoległe uruchomienia:** zakazane (blokada) czy dozwolone? Co, gdy admin doda próbki w trakcie działania pipeline'u?
28. **Rollback:** kiedy i kto cofa promocję (np. alarm driftu po promocji — ADR-0007)? Ile poprzednich wersji trzymamy?
29. **Budżet uruchomienia:** maks. czas i koszt jednego uruchomienia; twarde timeouty etapów.
30. **Awaria w połowie:** które etapy można wznowić, a które startują od zera? Jak wygląda stan uruchomienia w panelu (np. `GENERATING 120/300`, `TRAINING`, `EVALUATING`, `PROMOTED` / `REJECTED` / `FAILED`)?

---

## Definicja „gotowe”
- [ ] Każde pytanie ma odpowiedź albo zaplanowany spike z właścicielem.
- [ ] Propozycje ADR dla: triggera (1), puli (11–14), protokołu ewaluacji i reguły promocji (18–24).
- [ ] Diagram sekwencji retrainingu w `docs/architecture/`.
- [ ] Szkice JSON Schema: parametry joba, postęp, manifest datasetu, raport ewaluacji.
- [ ] Przegląd przez osobę spoza zespołu projektującego (np. Mikołaj).
