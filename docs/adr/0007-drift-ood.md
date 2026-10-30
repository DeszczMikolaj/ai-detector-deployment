# ADR-0007: Monitoring driftu i flaga OOD

- **Status:** przyjęta
- **Data:** 2026-10-29

## Decyzja
Przy treningu zapisujemy profil cech danych treningowych (percentyle per cecha) jako artefakt obok modelu.

- **Per zapytanie:** flaga `out_of_distribution`, gdy co najmniej jedna z najważniejszych cech (wg SHAP) lub co najmniej 3 dowolne cechy wypadają poza p1–p99 treningu; API zwraca listę `ood_features`.
- **Zbiorczo:** histogram wyników per tydzień i odsetek zapytań poza zakresem (must have); PSI/KS per cecha (nice to have).

## Uzasadnienie
Bez etykiet nie mierzymy accuracy, ale wykrywamy data/prediction drift — sygnał, kiedy zrobić ewaluację na etykietowanych próbkach i rozważyć retraining. Concept drift wymaga etykiet.

## Konsekwencje
- Progi do dostrojenia na podstawie testów z etykietą.
