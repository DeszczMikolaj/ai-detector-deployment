# ADR-0005: Panel admina, uwierzytelnianie, baza — mały EC2 + Docker Compose

- **Status:** przyjęta
- **Data:** 2026-10-29

## Decyzja
EC2 t3.small (x86) z Docker Compose: FastAPI (API admina), Postgres (wolumen EBS, backup `pg_dump` → S3), Caddy (TLS, reverse proxy). Obrazy budowane w CI i publikowane w ECR. Dostęp administracyjny przez SSM Session Manager (bez otwartego SSH).

## Uzasadnienie
Niski, przewidywalny koszt; prostota.

## Konsekwencje
- Akademicki skrót — single point of failure. Wersja produkcyjna: ECS + ALB + RDS, multi-AZ.

## Otwarte
- Postgres w kontenerze vs RDS (db.t4g.micro).
