"""Testy skryptu wdrożenia na fake kliencie Lambdy (bez AWS)."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deploy_inference as d  # noqa: E402

GOOD_BODY = {
    "label": "human",
    "ai_probability": 0.23,
    "explanation": {"top_features": [{"feature": f"f{i}"} for i in range(5)]},
    "model_version": "v1",
    "timing": {"cold_start": False, "init_seconds": None, "processing_ms": 48.0},
}


def http(status: int, body) -> dict:
    return {"Payload": io.BytesIO(json.dumps({"statusCode": status, "body": json.dumps(body)}).encode())}


class FakeLambda:
    def __init__(self, responses_for_text, *, alias_version="4", versions=("1", "4", "5"), state="Active"):
        self.responses_for_text = responses_for_text  # funkcja: (tekst, nr wywołania) -> odpowiedź invoke
        self.alias_version = alias_version
        self.versions = versions
        self.state = state
        self.invocations: list[tuple[str, str]] = []
        self.updates: list[dict] = []

    def invoke(self, FunctionName, Qualifier, Payload):
        text = json.loads(json.loads(Payload)["body"])["text"]
        self.invocations.append((Qualifier, text))
        response = self.responses_for_text(text, len(self.invocations))
        if isinstance(response, Exception):
            raise response
        return response

    def list_versions_by_function(self, FunctionName, Marker=None):
        return {"Versions": [{"Version": "$LATEST"}] + [{"Version": v} for v in self.versions]}

    def get_alias(self, FunctionName, Name):
        return {"FunctionVersion": self.alias_version, "RevisionId": "rev-1"}

    def get_function_configuration(self, FunctionName, Qualifier):
        return {"State": self.state, "CodeSha256": "abc", "Environment": {"Variables": {"MODEL_URI": "s3://b/models/v1/"}}}

    def update_alias(self, **kwargs):
        self.updates.append(kwargs)


def healthy(text, n):
    return http(400, {"error": "x"}) if not text.strip() else http(200, GOOD_BODY)


def run(client, **kwargs):
    defaults = dict(function="fn", alias="champion", version=None, expect_model_version=None,
                    attempts=3, wait_s=0, switch=True, log=lambda _: None)
    return d.deploy(client, **{**defaults, **kwargs})


def test_switches_alias_to_latest_version_after_smoke_test():
    client = FakeLambda(healthy)
    assert run(client) == "5"
    assert {q for q, _ in client.invocations} == {"5"}  # testujemy nową wersję, nie alias
    assert client.updates == [{"FunctionName": "fn", "Name": "champion", "FunctionVersion": "5", "RevisionId": "rev-1"}]


def test_warm_up_retries_after_cold_start_timeout():
    def flaky(text, n):
        if n == 1:
            return {"FunctionError": "Unhandled", "Payload": io.BytesIO(b'{"errorType":"Runtime.ExitError"}')}
        if n == 2:
            return TimeoutError("read timeout")
        return healthy(text, n)

    client = FakeLambda(flaky)
    assert run(client) == "5"
    assert len(client.updates) == 1


def test_gives_up_and_keeps_alias_when_version_never_answers():
    client = FakeLambda(lambda text, n: http(500, {"error": "x"}))
    with pytest.raises(d.DeployError, match="po 3 próbach"):
        run(client)
    assert client.updates == []


def test_smoke_test_rejects_wrong_model_version():
    client = FakeLambda(healthy)
    with pytest.raises(d.DeployError, match="model_version"):
        run(client, expect_model_version="v2")
    assert client.updates == []


def test_smoke_test_rejects_missing_explanation():
    body = {**GOOD_BODY, "explanation": {}}
    client = FakeLambda(lambda text, n: http(400, {}) if not text.strip() else http(200, body))
    with pytest.raises(d.DeployError, match="top_features"):
        run(client)
    assert client.updates == []


def test_smoke_test_requires_input_validation():
    client = FakeLambda(lambda text, n: http(200, GOOD_BODY))  # pusty tekst też daje 200
    with pytest.raises(d.DeployError, match="400"):
        run(client)
    assert client.updates == []


def test_no_switch_only_tests():
    client = FakeLambda(healthy)
    run(client, switch=False)
    assert client.updates == []


def test_explicit_version_for_rollback():
    client = FakeLambda(healthy, alias_version="5")
    assert run(client, version="4") == "4"
    assert client.updates[0]["FunctionVersion"] == "4"


def test_already_current_version_does_not_update():
    client = FakeLambda(healthy, alias_version="5")
    run(client)
    assert client.updates == []


def test_inactive_version_is_rejected():
    client = FakeLambda(healthy, state="Pending")
    with pytest.raises(d.DeployError, match="nie jest aktywna"):
        run(client)
    assert client.invocations == []
