# ADR-0006: Logowanie zapytań — asynchronicznie przez SQS, bez surowego tekstu klienta

- **Status:** przyjęta
- **Data:** 2026-10-29

## Decyzja
Lambda wysyła wpis do SQS i zwraca odpowiedź; consumer na EC2 zapisuje wpisy paczkami do Postgresa.

- **Zawartość wpisu (ruch klientów):** znacznik czasu, wersja modelu, wynik, wektor cech, długość tekstu, hash tekstu. **Bez surowego tekstu** (ochrona danych / RODO).
- **Ścieżka admina:** osobny endpoint ewaluacji próbek z etykietą (tekst + etykieta), osobna tabela — nie miesza się ze statystykami ruchu klientów.
- **Retencja:** okno czasowe (np. 90 dni), codzienne zadanie czyszczące.

## Uzasadnienie
Brak połączeń Lambda → Postgres (limit połączeń, odporność na awarię bazy), brak wpływu logowania na latencję.
