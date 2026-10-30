# System Detekcji Tekstów AI — kontekst projektu

## Charakter projektu
Projekt wdrożeniowy (inżynieryjny, nie tylko badawczy). System ma odzwierciedlać standardy produkcyjne: wydajność, bezpieczeństwo, niezawodność, utrzymywalność i obserwowalność są wymaganiami równorzędnymi z jakością modelu.

## Funkcje systemu

### 1. Część kliencka (inference)
- Klient dostarcza próbkę tekstu i otrzymuje ocenę: tekst wygenerowany przez AI czy napisany przez człowieka.
- Ocenę wykonuje wytrenowany model klasyfikujący (aktualnie wypromowana wersja).
- Pipeline modelu oceniającego już istnieje — trzeba go osadzić w systemie (serwowanie, API, wersjonowanie).

### 2. Część administracyjna (retraining / MLOps)
- Administrator dodaje nowe próbki tekstów pisanych przez człowieka.
- Dodanie próbek uruchamia pipeline:
  1. przyjęcie i walidacja nowych próbek ludzkich,
  2. wygenerowanie odpowiadających im próbek AI,
  3. włączenie ich do zbioru treningowego i trening nowego modelu,
  4. porównanie nowego modelu z obecnym (champion vs challenger) na ustalonych metrykach,
  5. promocja nowego modelu tylko, jeśli ma lepsze charakterystyki; w przeciwnym razie zostaje stary.
- Docelowo: możliwość wyboru jednego z kilku lokalnych modeli językowych używanych w pipeline (np. jako generator próbek AI).

### 3. Kontrola puli treningowej
- Zbiór treningowy nie może rosnąć bez ograniczeń.
- Potrzebny mechanizm zawężania/selekcji puli (np. limit rozmiaru, deduplikacja, selekcja reprezentatywnych lub najbardziej informatywnych próbek, retencja) — do zaprojektowania.

## Wymagania niefunkcjonalne
- Wydajność: czas odpowiedzi części klienckiej, obsługa obciążenia, oddzielenie ciężkich zadań (generacja, trening) od ścieżki inference.
- Bezpieczeństwo: uwierzytelnianie i autoryzacja (rozdział ról klient/admin), walidacja wejścia, limity zapytań, ochrona danych.
- Reprodukowalność i wersjonowanie: modele, zbiory danych, konfiguracje i wyniki ewaluacji.
- Obserwowalność: logi, metryki, monitoring jakości modelu.
- Niezawodność: bezpieczna promocja i możliwość wycofania modelu.

## Stan obecny
- Gotowy pipeline modelu oceniającego tekst.
- Pozostała architektura systemu do zaprojektowania i implementacji.

## Kwestie otwarte
- Dokładna rola wyboru lokalnego modelu (generator próbek AI czy coś więcej).
- Metryki i próg decyzji o promocji modelu.
- Strategia ograniczania puli treningowej.
- Stos technologiczny, sposób wdrożenia, podział pracy w zespole.
