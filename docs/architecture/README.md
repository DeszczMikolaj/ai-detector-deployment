# Architektura systemu

Diagramy w [Mermaid](https://mermaid.js.org/) — źródło jest w tym pliku, GitHub renderuje je automatycznie. Wyrenderowane obrazy trafiają do lustra w Confluence (TAI-DETEKTOR → Architektura).

Poziomy według modelu [C4](https://c4model.com/):
1. Diagram kontekstu — _do zrobienia_
2. **Diagram kontenerów** — poniżej
3. Przepływy (sekwencje): ocena tekstu, retraining — _do zrobienia_

## Diagram kontenerów

Stan na 2026-10-31. Region AWS: eu-central-1 (ADR-0008).

```mermaid
flowchart LR
    %% ===== Aktorzy =====
    client(["👤 Klient"])
    admin(["🛠️ Administrator"])

    %% ===== Cloudflare =====
    subgraph CF["Cloudflare"]
        fe["<b>Frontend</b><br/>Cloudflare Pages<br/><i>UI klienta + panel admina</i>"]
        proxy["<b>Proxy / DNS / TLS</b>"]
    end

    %% ===== AWS =====
    subgraph AWS["AWS · eu-central-1"]
        subgraph INF["Ścieżka inference · ADR-0004"]
            apigw["<b>API Gateway</b><br/><i>throttling = rate limit</i>"]
            lambda["<b>Lambda: inference</b><br/>container image<br/>spaCy + packages/features + XGBoost<br/><i>alias: champion</i>"]
        end

        sqs[["<b>SQS</b><br/>logi zapytań<br/><i>bez surowego tekstu · ADR-0006</i>"]]

        subgraph EC2["EC2 t3.small · Docker Compose · ADR-0005"]
            caddy["<b>Caddy</b><br/>TLS, reverse proxy :443"]
            adminapi["<b>admin-api</b><br/>FastAPI<br/>+ consumer SQS"]
            pg[("<b>Postgres</b><br/>próbki, joby,<br/>rejestr modeli, logi")]
        end

        subgraph BATCH["AWS Batch · ADR-0003 / ADR-0010"]
            qspot[["kolejka <b>spot</b><br/><i>domyślna</i>"]]
            qod[["kolejka <b>ondemand</b><br/><i>tryb awaryjny</i>"]]
            workers["<b>Workery pipeline'u</b><br/>EC2 CPU · skalowanie do zera<br/>generacja LLM (llama.cpp / Ollama)<br/>trening XGBoost · ewaluacja"]
        end

        s3[("<b>S3</b><br/>modele, profile cech,<br/>datasety, próbki, backupy")]
        ecr[("<b>ECR</b><br/>obrazy: Lambda,<br/>workery, admin-api")]
        cw["<b>CloudWatch</b><br/>logi i metryki wszystkich usług,<br/>alarmy, Budgets"]
    end

    %% ===== Zewnętrzne =====
    hf["<b>Hugging Face</b><br/>wagi lokalnych LLM"]
    gh["<b>GitHub Actions</b><br/>CI/CD · OIDC"]

    %% ===== Przepływ: klient =====
    client -->|"HTTPS"| fe
    fe -->|"POST /evaluate"| apigw
    apigw --> lambda
    lambda -.->|"wpis logu"| sqs

    %% ===== Przepływ: admin =====
    admin -->|"HTTPS"| fe
    fe -->|"API admina"| proxy
    proxy --> caddy
    caddy --> adminapi
    adminapi --> pg
    sqs -.->|"odbiór paczkami"| adminapi

    %% ===== Retraining =====
    adminapi -->|"SubmitJob<br/>(wybór kolejki)"| qspot
    adminapi -->|"SubmitJob"| qod
    qspot --> workers
    qod --> workers
    workers <-->|"próbki, modele,<br/>metryki"| s3
    workers -.->|"status joba"| adminapi
    adminapi -->|"promocja:<br/>przełączenie aliasu"| lambda

    %% ===== Artefakty i infrastruktura =====
    lambda -.->|"model championa"| s3
    adminapi -.->|"pg_dump"| s3
    hf -.->|"pobranie wag"| s3
    gh -->|"push obrazów"| ecr

    %% ===== Style =====
    classDef actor fill:#E3FCEF,stroke:#36B37E,color:#172B4D
    classDef ext fill:#F4F5F7,stroke:#97A0AF,color:#172B4D
    classDef store fill:#FFFAE6,stroke:#FFC400,color:#172B4D
    classDef compute fill:#DEEBFF,stroke:#4C9AFF,color:#172B4D
    classDef queue fill:#EAE6FF,stroke:#6554C0,color:#172B4D
    class client,admin actor
    class hf,gh,fe,proxy ext
    class s3,ecr,pg store
    class apigw,lambda,caddy,adminapi,workers,cw compute
    class sqs,qspot,qod queue
```

**Legenda:** linia ciągła — wywołanie synchroniczne; przerywana — asynchroniczne / dostęp do artefaktów.

### Kluczowe granice
- **Inference jest odcięte od ciężkiej pracy.** Lambda nie dotyka Postgresa ani Batcha — tylko zwraca wynik i wrzuca log do SQS.
- **Publiczne API nie tworzy instancji.** admin-api jedynie zleca joby do kolejek Batch; cyklem życia instancji zarządza Batch.
- **Jedno źródło cech.** Lambda i workery używają tego samego `packages/features/` (ADR-0002).

## Luki, które ujawnił diagram (do decyzji)

1. **Uwierzytelnianie i role klient/admin** — wymagane przez `kontekst-projektu.md`, nieustalone. Kandydaci: Amazon Cognito vs własne JWT w admin-api. Dotyczy też tego, czy ocena tekstu wymaga logowania.
2. **Jak Lambda dostaje model championa.** ADR-0004 zakłada model „zapieczony w obrazie”, ale wtedy promocja wymaga zbudowania nowego obrazu — a workery Batch nie powinny budować obrazów. Kandydat: spaCy w obrazie, model XGBoost + profil cech pobierane z S3 w fazie init; wersja modelu jako zmienna środowiskowa **wersji** Lambdy, promocja = opublikowanie nowej wersji + przełączenie aliasu. Koszt: dłuższy cold start o pobranie małego pliku.
3. **Status jobów:** callback workerów do admin-api vs polling Batch / EventBridge. Wpływa na to, czy workery potrzebują dostępu sieciowego do EC2.
4. **Skąd workery biorą wagi LLM** — pobieranie z Hugging Face przy każdym jobie vs cache w S3 (kilka GB na model).
