# ADR-0014: Lustro wag lokalnych LLM w S3 z przypiętymi wersjami

- **Status:** przyjęta
- **Data:** 2026-10-31

## Kontekst
Workery generacji (ADR-0010) to świeże instancje przy każdym uruchomieniu (skalowanie do zera) — nie mają wag modelu na dysku. Wagi modelu ~7–8B w kwantyzacji 4-bit to ok. 5 GB na model. `kontekst-projektu.md` wymaga możliwości wyboru jednego z kilku lokalnych modeli.

## Decyzja
1. **Wagi LLM kopiujemy raz** (ręcznie lub skryptem administracyjnym) z Hugging Face do naszego bucketa S3, np. `s3://…/llm/<rodzina>/<wersja>/`. Każdy wpis ma metadane: źródło (repozytorium i rewizja na HF), kwantyzacja, rozmiar, **suma kontrolna SHA-256**, licencja.
2. **Katalog dostępnych modeli** (rejestr w Postgresie) jest źródłem listy w panelu admina — admin wybiera generator z modeli obecnych w lustrze.
3. **Każdy job pobiera wagi z S3** na dysk instancji na starcie i weryfikuje sumę kontrolną. Bez cache'u na start; czas pobierania mierzymy przy pierwszym uruchomieniu na AWS.
4. **Każda wygenerowana próbka** zapisuje w metadanych identyfikator i wersję modelu-generatora oraz parametry generacji (seed, temperatura, prompt/szablon).
5. Workery **nie łączą się z Hugging Face** w czasie działania.

## Uzasadnienie
- **Powtarzalność:** przypięta wersja i suma kontrolna — model nie zmieni się „pod nami”, nawet jeśli autor podmieni lub usunie go na HF.
- **Niezawodność:** brak zależności od zewnętrznej usługi w trakcie pipeline'u.
- **Koszt i czas:** transfer S3 → EC2 w tym samym regionie jest bezpłatny; pobrania w równoległych jobach idą jednocześnie; szacunkowo ~1 min na job wobec ~50 min generacji porcji 25 próbek (~2% narzutu). Przechowywanie kilku modeli po ~5 GB — rząd kilkudziesięciu centów miesięcznie.

## Konsekwencje / trade-offy
- Dodanie nowego modelu to świadoma operacja administracyjna (kopiowanie + wpis w katalogu), nie wybór dowolnej nazwy z HF.
- Trzeba sprawdzić licencje modeli (np. warunki użycia PLLuM, Bielika, Qwena) przy dodawaniu do lustra.
- Dysk instancji workera musi pomieścić wagi + robocze pliki (EBS ≥ ~30 GB w szablonie compute environment).
- Jeśli pomiar pokaże, że pobieranie istotnie wydłuża pipeline: kolejno większe porcje → cache na dysku hosta współdzielony przez joby na tej samej instancji → własne AMI z wagami.

## Rozważone alternatywy
| Opcja | Powód odrzucenia |
|---|---|
| Pobieranie z Hugging Face przy każdym jobie | Zależność zewnętrzna (awarie, limity), brak gwarancji niezmienności modelu |
| Wagi w obrazie Dockera workera | Obraz kilka GB na model, wolne pobieranie z ECR, przebudowa przy każdej zmianie modelu |
| Własne AMI z wagami | Zero pobierania, ale utrzymanie AMI to przerost formy przy obecnej skali |
