"""Bezpieczne przełączenie aliasu `champion` Lambdy inference na nową wersję (ADR-0012, pkt 4).

Terraform publikuje nową wersję Lambdy, ale aliasu nie rusza (`ignore_changes`). Ten skrypt:
  1. wywołuje nową wersję BEZPOŚREDNIO (z pominięciem API Gateway — klienci jej nie widzą),
     aż przejdzie cold start (pierwsze starty świeżego obrazu mogą trwać > 10 s),
  2. robi test dymny: poprawna ocena tekstu, odrzucenie pustego wejścia, oczekiwana wersja modelu,
  3. dopiero wtedy przełącza alias `champion` (z blokadą optymistyczną RevisionId).
Przy niepowodzeniu alias zostaje bez zmian. Rollback = ten sam skrypt z `--version <poprzednia>`.

Użycie (PowerShell, z katalogu głównego repo, po `terraform apply`):
    python scripts/deploy_inference.py                     # najnowsza opublikowana wersja
    python scripts/deploy_inference.py --version 5         # konkretna wersja (np. rollback)
    python scripts/deploy_inference.py --no-switch         # tylko rozgrzanie i test

Wymaga: boto3[crt] (rozszerzenie crt obsługuje sesję z `aws login`) albo kluczy w zmiennych AWS_* (export-credentials).
Uprawnienia: lambda:InvokeFunction, GetAlias, UpdateAlias, GetFunctionConfiguration, ListVersionsByFunction.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass

DEFAULT_FUNCTION = "ai-text-detector-inference"
DEFAULT_ALIAS = "champion"
DEFAULT_REGION = "eu-north-1"

SMOKE_TEXT = (
    "Wczoraj wieczorem poszedłem do kina. Film był długi, ale bardzo ciekawy i dobrze zagrany. "
    "Po seansie rozmawialiśmy o nim jeszcze przez godzinę, siedząc w małej kawiarni na rogu ulicy."
)
WARM_CALLS = 3  # ile udanych wywołań po rozgrzaniu (stabilność + czasy warm)


class DeployError(RuntimeError):
    pass


@dataclass
class Invocation:
    ok: bool
    status: int | None  # statusCode z odpowiedzi handlera
    body: dict | None
    error: str | None
    seconds: float


def _event(text: str) -> dict:
    """Zdarzenie w formacie HTTP API (payload 2.0) — handler czyta tylko `body`."""
    return {"body": json.dumps({"text": text}, ensure_ascii=False), "isBase64Encoded": False}


def invoke(client, function: str, version: str, text: str) -> Invocation:
    started = time.perf_counter()
    try:
        response = client.invoke(
            FunctionName=function,
            Qualifier=version,
            Payload=json.dumps(_event(text), ensure_ascii=False).encode("utf-8"),
        )
    except Exception as exc:  # noqa: BLE001 — np. timeout połączenia przy długim cold starcie
        return Invocation(False, None, None, f"{type(exc).__name__}: {exc}", time.perf_counter() - started)

    seconds = time.perf_counter() - started
    raw = response["Payload"].read()
    if response.get("FunctionError"):
        return Invocation(False, None, None, f"FunctionError: {raw[:300]!r}", seconds)

    payload = json.loads(raw)
    try:
        body = json.loads(payload.get("body") or "null")
    except ValueError:
        body = None
    return Invocation(payload.get("statusCode") == 200, payload.get("statusCode"), body, None, seconds)


def check_evaluation(body: dict | None, expect_model_version: str | None) -> list[str]:
    """Kontrakt odpowiedzi 200 (services/inference/README.md). Zwraca listę problemów."""
    if not isinstance(body, dict):
        return ["odpowiedź nie jest obiektem JSON"]
    problems = []
    if body.get("label") not in {"ai", "human"}:
        problems.append(f"label={body.get('label')!r}")
    p = body.get("ai_probability")
    if not isinstance(p, (int, float)) or not 0.0 <= p <= 1.0:
        problems.append(f"ai_probability={p!r}")
    top = (body.get("explanation") or {}).get("top_features")
    if not isinstance(top, list) or len(top) != 5:
        problems.append("explanation.top_features nie ma 5 elementów")
    if expect_model_version and body.get("model_version") != expect_model_version:
        problems.append(f"model_version={body.get('model_version')!r}, oczekiwano {expect_model_version!r}")
    return problems


def latest_version(client, function: str) -> str:
    versions, marker = [], None
    while True:
        kwargs = {"FunctionName": function, **({"Marker": marker} if marker else {})}
        page = client.list_versions_by_function(**kwargs)
        versions += [v["Version"] for v in page["Versions"] if v["Version"] != "$LATEST"]
        marker = page.get("NextMarker")
        if not marker:
            break
    if not versions:
        raise DeployError("Funkcja nie ma żadnej opublikowanej wersji")
    return str(max(int(v) for v in versions))


def warm_up(client, function: str, version: str, attempts: int, wait_s: float, log) -> Invocation:
    """Wywołuje wersję, aż odpowie 200. Pierwsze próby po wdrożeniu mogą kończyć się timeoutem init."""
    for attempt in range(1, attempts + 1):
        result = invoke(client, function, version, SMOKE_TEXT)
        timing = (result.body or {}).get("timing", {}) if isinstance(result.body, dict) else {}
        log(f"  próba {attempt}/{attempts}: {'OK' if result.ok else 'błąd'} w {result.seconds:.1f} s"
            + (f", cold_start={timing.get('cold_start')}, init={timing.get('init_seconds')} s" if timing else "")
            + (f" — {result.error}" if result.error else ""))
        if result.ok:
            return result
        if attempt < attempts:
            time.sleep(wait_s)
    raise DeployError(f"Wersja {version} nie odpowiedziała poprawnie po {attempts} próbach")


def smoke_test(client, function: str, version: str, expect_model_version: str | None, log) -> None:
    for i in range(1, WARM_CALLS + 1):
        result = invoke(client, function, version, SMOKE_TEXT)
        problems = check_evaluation(result.body, expect_model_version) if result.ok else [result.error or f"status {result.status}"]
        if problems:
            raise DeployError(f"Test dymny, wywołanie {i}: " + "; ".join(problems))
        timing = result.body.get("timing", {})
        log(f"  ocena {i}/{WARM_CALLS}: {result.body['label']} ({result.body['ai_probability']}), "
            f"model {result.body.get('model_version')}, processing {timing.get('processing_ms')} ms")

    rejected = invoke(client, function, version, "   ")
    if rejected.status != 400:
        raise DeployError(f"Test dymny: pusty tekst powinien dać 400, jest {rejected.status} {rejected.error or ''}")
    log("  walidacja wejścia: pusty tekst → 400 OK")


def deploy(client, *, function: str, alias: str, version: str | None, expect_model_version: str | None,
           attempts: int, wait_s: float, switch: bool, log=print) -> str:
    target = version or latest_version(client, function)
    current = client.get_alias(FunctionName=function, Name=alias)
    log(f"Alias {alias} → wersja {current['FunctionVersion']}; cel: wersja {target}")

    config = client.get_function_configuration(FunctionName=function, Qualifier=target)
    if config.get("State") != "Active":
        raise DeployError(f"Wersja {target} nie jest aktywna (State={config.get('State')})")
    log(f"Wersja {target}: obraz {config.get('CodeSha256', '')[:12]}…, "
        f"MODEL_URI={config.get('Environment', {}).get('Variables', {}).get('MODEL_URI')}")

    log("1/3 Rozgrzewanie (wywołania bezpośrednio wersji, poza API Gateway)")
    warm_up(client, function, target, attempts, wait_s, log)

    log("2/3 Test dymny")
    smoke_test(client, function, target, expect_model_version, log)

    if not switch:
        log("3/3 Pominięte (--no-switch) — alias bez zmian")
        return target
    if current["FunctionVersion"] == target:
        log(f"3/3 Alias {alias} już wskazuje wersję {target} — bez zmian")
        return target

    # RevisionId: jeśli ktoś przestawił alias w międzyczasie, AWS odrzuci zmianę zamiast ją nadpisać.
    client.update_alias(FunctionName=function, Name=alias, FunctionVersion=target, RevisionId=current["RevisionId"])
    log(f"3/3 Alias {alias}: wersja {current['FunctionVersion']} → {target}")
    log(f"Rollback: python scripts/deploy_inference.py --version {current['FunctionVersion']}")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", help="wersja Lambdy (domyślnie najnowsza opublikowana)")
    parser.add_argument("--function", default=DEFAULT_FUNCTION)
    parser.add_argument("--alias", default=DEFAULT_ALIAS)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--expect-model-version", help="np. v1 — test sprawdzi model_version w odpowiedzi")
    parser.add_argument("--attempts", type=int, default=6, help="maks. prób rozgrzania")
    parser.add_argument("--wait", type=float, default=5.0, help="przerwa między próbami (s)")
    parser.add_argument("--no-switch", action="store_true", help="tylko rozgrzanie i test, bez przełączania aliasu")
    args = parser.parse_args(argv)

    import boto3
    from botocore.config import Config

    # read_timeout > timeout Lambdy: przy pierwszym starcie nowego obrazu init + wywołanie trwa do ~35 s.
    client = boto3.client("lambda", region_name=args.region,
                          config=Config(read_timeout=150, connect_timeout=10, retries={"max_attempts": 1}))
    try:
        deploy(client, function=args.function, alias=args.alias, version=args.version,
               expect_model_version=args.expect_model_version, attempts=args.attempts, wait_s=args.wait,
               switch=not args.no_switch)
    except DeployError as exc:
        print(f"PRZERWANO: {exc}. Alias bez zmian.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
