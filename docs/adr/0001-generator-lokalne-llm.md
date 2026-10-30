# ADR-0001: Generator próbek AI — lokalne LLM-y, bez zewnętrznego API

- **Status:** przyjęta
- **Data:** 2026-10-29

## Decyzja
Próbki AI generujemy lokalnymi modelami językowymi (z możliwością wyboru modelu). Nie korzystamy z zewnętrznych API (np. ChatGPT).

## Uzasadnienie
Wymóg prowadzącego — system ma odzwierciedlać środowisko produkcyjne z wyborem lokalnych LLM-ów. Zgodne z `docs/kontekst-projektu.md`.

## Konsekwencje
- Generacja wymaga GPU → osobny, efemeryczny worker (ADR-0003).
- Nowe konta AWS mają domyślnie quotę 0 vCPU dla instancji G/VT → wniosek o podniesienie limitu (On-Demand i Spot) składamy od razu po założeniu konta.
- Plan B: worker jako kontener niezależny od miejsca uruchomienia (możliwość uruchomienia na lokalnym GPU członka zespołu).
