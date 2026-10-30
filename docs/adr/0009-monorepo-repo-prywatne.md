# ADR-0009: Monorepo na prywatnym koncie GitHub właściciela

- **Status:** przyjęta
- **Data:** 2026-10-30

## Decyzja
Cały kod, IaC i dokumentacja w jednym repozytorium (monorepo), należącym do osobistego konta GitHub właściciela projektu. Pozostali członkowie zespołu są zapraszani jako kontrybutorzy (collaborators). Nie zakładamy organizacji GitHub.

## Uzasadnienie
- Monorepo: ekstrakcja cech musi być identyczna w treningu i inference (ADR-0002) — jeden pakiet `packages/features/` importowany przez oba miejsca, bez publikowania wspólnej biblioteki. Jedno CI, IaC obok kodu, jeden `AGENTS.md`.
- Konto osobiste: prostsza administracja przy małym zespole.

## Konsekwencje / trade-offy
- Na repo osobistym kontrybutorzy mają jeden poziom uprawnień (write); ustawienia, sekrety Actions i konfigurację OIDC zmienia tylko właściciel — wąskie gardło i bus factor = 1.
- **Ochrona gałęzi `main` na prywatnym repo wymaga planu GitHub Pro** (na planie Free reguły nie są egzekwowane). Plan: Pro przez GitHub Student Developer Pack. Reguła: wymagany PR z 1 review, blokada force-push i usuwania, bez wyjątków dla administratora.
- Do czasu włączenia ochrony obowiązuje konwencja „bez pushy na `main`” (AGENTS.md).
- Migracja do organizacji później jest możliwa (transfer repo) bez utraty historii.
