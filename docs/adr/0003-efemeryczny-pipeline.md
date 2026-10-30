# ADR-0003: Ciężki pipeline (generacja, trening, ewaluacja) — efemeryczne zasoby obliczeniowe

- **Status:** przyjęta co do zasady (szczegóły do doprecyzowania)
- **Data:** 2026-10-29

## Decyzja
Pipeline administracyjny uruchamiany na żądanie, na zasobach skalowanych do zera (kandydat: AWS Batch z EC2 GPU/Spot, min vCPU = 0, twardy timeout).

## Uzasadnienie
Duża dysproporcja obciążenia między inference a retrainingiem; brak potrzeby stale działającej dużej instancji.

## Konsekwencje
- Ryzyko „zombie-instancji” → timeouty, alerty budżetowe.
- Publiczne API nie ma uprawnień do bezpośredniego tworzenia instancji.
