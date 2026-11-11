"""Testy inference: weryfikacja artefaktu (ADR-0012), flaga OOD (ADR-0007), kontrakt API handlera.

Artefakt testowy budujemy w formacie `pipelines/retraining/train.py` na losowych danych.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest
import xgboost as xgb

from app import artifact
from detector_features import DEFAULT_SPACY_MODEL, FEATURE_NAMES, FEATURE_SCHEMA_VERSION, N_FEATURES

HAS_SPACY_MODEL = importlib.util.find_spec(DEFAULT_SPACY_MODEL) is not None
SPACY_MODEL_VERSION = importlib.metadata.version(DEFAULT_SPACY_MODEL) if HAS_SPACY_MODEL else "3.8.0"
needs_spacy_model = pytest.mark.skipif(not HAS_SPACY_MODEL, reason=f"brak modelu {DEFAULT_SPACY_MODEL}")

TEXT = "Wczoraj wieczorem poszedłem do kina. Film był długi, ale bardzo ciekawy i dobrze zagrany. " * 3


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_artifact(directory: Path, *, seed: int = 0) -> Path:
    """Mały model na losowych danych + profil, metadane i sumy — jak train.py."""
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(400, N_FEATURES))
    y = (X[:, 4] + 0.5 * X[:, 0] > 0).astype(int)  # model zależy głównie od cech 4 i 0

    booster = xgb.train({"objective": "binary:logistic", "max_depth": 3, "seed": seed}, xgb.DMatrix(X, label=y), num_boost_round=20)
    booster.save_model(directory / "model.ubj")

    profile = {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "n_samples": len(X),
        "features": {
            name: {"p1": float(np.percentile(X[:, j], 1)), "p99": float(np.percentile(X[:, j], 99))}
            for j, name in enumerate(FEATURE_NAMES)
        },
    }
    (directory / "feature_profile.json").write_text(json.dumps(profile), encoding="utf-8")

    metadata = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": list(FEATURE_NAMES),
        "spacy": {"version": "3.8.13", "model": DEFAULT_SPACY_MODEL, "model_version": SPACY_MODEL_VERSION},
        "xgboost_version": xgb.__version__,
        "decision_threshold": 0.5,
        "label_meaning": {"0": "human", "1": "ai"},
    }
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    checksums = {name: _sha256(directory / name) for name in artifact.ARTIFACT_FILES}
    (directory / "checksums.json").write_text(json.dumps(checksums), encoding="utf-8")
    return directory


def load(directory: Path, **kwargs) -> artifact.ModelArtifact:
    return artifact.load(str(directory), spacy_model=DEFAULT_SPACY_MODEL, spacy_model_version=SPACY_MODEL_VERSION, **kwargs)


def rewrite_json(directory: Path, name: str, change) -> None:
    """Zmienia plik JSON artefaktu i aktualizuje sumę — testuje walidację treści, nie sum."""
    path = directory / name
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")
    sums = json.loads((directory / "checksums.json").read_text(encoding="utf-8"))
    sums[name] = _sha256(path)
    (directory / "checksums.json").write_text(json.dumps(sums), encoding="utf-8")


@pytest.fixture
def model_dir(tmp_path: Path) -> Path:
    return write_artifact(tmp_path / "models" / "v7")


# ---------- weryfikacja artefaktu ----------


def test_valid_artifact_loads(model_dir):
    model = load(model_dir)
    assert model.version == "v7"
    assert model.threshold == 0.5
    assert len(model.top_features) <= artifact.OOD_TOP_K
    assert 4 in model.top_features  # cecha, od której zależą etykiety


def test_tampered_model_is_rejected(model_dir):
    with (model_dir / "model.ubj").open("ab") as f:
        f.write(b"\0")
    with pytest.raises(artifact.ArtifactError, match="SHA-256"):
        load(model_dir)


def test_missing_file_is_rejected(model_dir):
    (model_dir / "feature_profile.json").unlink()
    with pytest.raises(artifact.ArtifactError, match="Brak pliku"):
        load(model_dir)


def test_unexpected_entry_in_checksums_is_rejected(model_dir):
    sums = json.loads((model_dir / "checksums.json").read_text())
    sums["../../etc/passwd"] = "0" * 64
    (model_dir / "checksums.json").write_text(json.dumps(sums))
    with pytest.raises(artifact.ArtifactError, match="dokładnie"):
        load(model_dir)


def test_other_feature_schema_is_rejected(model_dir):
    rewrite_json(model_dir, "metadata.json", lambda m: m.update(feature_schema_version="1"))
    with pytest.raises(artifact.ArtifactError, match="Schemat cech"):
        load(model_dir)


def test_reordered_features_are_rejected(model_dir):
    rewrite_json(model_dir, "metadata.json", lambda m: m["feature_names"].reverse())
    with pytest.raises(artifact.ArtifactError, match="kolejność"):
        load(model_dir)


def test_other_spacy_model_is_rejected(model_dir):
    rewrite_json(model_dir, "metadata.json", lambda m: m["spacy"].update(model="pl_core_news_lg"))
    with pytest.raises(artifact.ArtifactError, match="trenowano"):
        load(model_dir)


# ---------- pobieranie z S3 ----------


class FakeS3:
    def __init__(self, source: Path):
        self.source = source
        self.requested: list[tuple[str, str]] = []

    def download_file(self, bucket, key, filename):
        self.requested.append((bucket, key))
        shutil.copy(self.source / key.rsplit("/", 1)[-1], filename)


def test_fetch_from_s3_downloads_only_known_files(model_dir, tmp_path):
    s3 = FakeS3(model_dir)
    model = artifact.load(
        "s3://bucket/models/v7/",
        spacy_model=DEFAULT_SPACY_MODEL,
        spacy_model_version=SPACY_MODEL_VERSION,
        workdir=tmp_path / "download",
        s3_client=s3,
    )
    assert model.version == "v7"
    assert sorted(key for _, key in s3.requested) == sorted(
        f"models/v7/{name}" for name in ("checksums.json", *artifact.ARTIFACT_FILES)
    )
    assert {bucket for bucket, _ in s3.requested} == {"bucket"}


# ---------- predykcja i OOD ----------


def test_prediction_matches_booster(model_dir):
    model = load(model_dir)
    booster = xgb.Booster(model_file=str(model_dir / "model.ubj"))
    x = np.zeros(N_FEATURES)
    x[4] = 1.0
    expected = float(booster.predict(xgb.DMatrix(x.reshape(1, -1)))[0])
    pred = model.predict(x)
    assert pred.ai_probability == pytest.approx(expected)
    assert pred.label == ("ai" if expected >= 0.5 else "human")


def test_typical_sample_is_not_ood(model_dir):
    pred = load(model_dir).predict(np.zeros(N_FEATURES))
    assert not pred.out_of_distribution
    assert pred.ood_features == ()


def test_two_unimportant_features_out_of_range_is_not_ood(model_dir):
    model = load(model_dir)
    unimportant = [i for i in range(N_FEATURES) if i not in model.top_features][:2]
    x = np.zeros(N_FEATURES)
    x[unimportant] = 100.0
    pred = model.predict(x)
    assert len(pred.ood_features) == 2
    assert not pred.out_of_distribution


def test_three_features_out_of_range_is_ood(model_dir):
    model = load(model_dir)
    unimportant = [i for i in range(N_FEATURES) if i not in model.top_features][:3]
    x = np.zeros(N_FEATURES)
    x[unimportant] = -100.0
    assert model.predict(x).out_of_distribution


def test_one_important_feature_out_of_range_is_ood(model_dir):
    model = load(model_dir)
    x = np.zeros(N_FEATURES)
    x[model.top_features[0]] = 100.0
    pred = model.predict(x)
    assert pred.out_of_distribution
    assert pred.ood_features == (FEATURE_NAMES[model.top_features[0]],)


# ---------- wyjaśnienie SHAP (ADR-0016) ----------


def test_explanation_is_top5_by_abs_shap_and_consistent_with_model(model_dir):
    model = load(model_dir)
    x = np.zeros(N_FEATURES)
    x[4], x[0] = 2.0, -1.5
    pred = model.predict(x)

    contribs = model.contributions(x)
    margin = float(model.booster.predict(xgb.DMatrix(x.reshape(1, -1)), output_margin=True)[0])
    assert contribs.sum() == pytest.approx(margin, abs=1e-4)  # SHAP + bias = logit
    assert pred.base_value == pytest.approx(float(contribs[-1]))

    top = pred.top_contributions
    assert len(top) == artifact.EXPLAIN_TOP_K
    assert [abs(c.shap) for c in top] == sorted((abs(c.shap) for c in top), reverse=True)
    assert top[0].feature == FEATURE_NAMES[4]  # cecha decydująca o etykietach
    assert top[0].value == 2.0
    assert top[0].towards == "ai" and top[0].shap > 0
    assert all(c.towards == ("ai" if c.shap > 0 else "human" if c.shap < 0 else None) for c in top)
    assert pred.shap_ms >= 0


def test_approx_shap_method(model_dir):
    pred = load(model_dir, shap_method="approx").predict(np.zeros(N_FEATURES))
    assert len(pred.top_contributions) == artifact.EXPLAIN_TOP_K


def test_unknown_shap_method_is_rejected(model_dir):
    with pytest.raises(artifact.ArtifactError, match="metoda SHAP"):
        load(model_dir, shap_method="fast")


def test_ood_uses_shap_ranking_from_metadata_when_present(model_dir):
    ranking = [FEATURE_NAMES[i] for i in (30, 31, 32, 33, 34, 35)]
    rewrite_json(model_dir, "metadata.json", lambda m: m.update(feature_importance={"method": "mean_abs_shap", "ranking": ranking}))
    model = load(model_dir)
    assert model.top_features_source == "mean_abs_shap"
    assert model.top_features == (30, 31, 32, 33, 34)

    x = np.zeros(N_FEATURES)
    x[30] = 100.0
    assert model.predict(x).out_of_distribution


def test_v1_artifact_without_ranking_falls_back_to_gain(model_dir):
    assert load(model_dir).top_features_source == "total_gain"


def test_unknown_feature_in_ranking_is_rejected(model_dir):
    rewrite_json(model_dir, "metadata.json", lambda m: m.update(feature_importance={"ranking": ["Nie_Ma_Takiej"]}))
    with pytest.raises(artifact.ArtifactError, match="nieznane cechy"):
        load(model_dir)


# ---------- handler (kontrakt API) ----------


@pytest.fixture
def handler_module(model_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_URI", str(model_dir))
    monkeypatch.setenv("MAX_TEXT_CHARS", "1000")
    sys.modules.pop("app.handler", None)
    return importlib.import_module("app.handler")


def _event(body) -> dict:
    return {"body": body if isinstance(body, str) else json.dumps(body)}


@needs_spacy_model
def test_handler_returns_prediction(handler_module, capsys):
    response = handler_module.handler(_event({"text": TEXT}), None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["label"] in {"ai", "human"}
    assert 0.0 <= body["ai_probability"] <= 1.0
    assert isinstance(body["out_of_distribution"], bool)
    assert set(body["ood_features"]) <= set(FEATURE_NAMES)
    assert body["model_version"] == "v7"
    assert body["feature_schema_version"] == FEATURE_SCHEMA_VERSION

    explanation = body["explanation"]
    assert explanation["method"] == "shap_exact"
    assert len(explanation["top_features"]) == 5
    assert {"feature", "value", "shap", "towards"} == set(explanation["top_features"][0])
    assert all(f["feature"] in FEATURE_NAMES and f["towards"] in {"ai", "human", None} for f in explanation["top_features"])
    assert body["timing"]["cold_start"] is True

    second = json.loads(handler_module.handler(_event({"text": TEXT}), None)["body"])
    assert second["timing"]["cold_start"] is False
    assert second["ai_probability"] == body["ai_probability"]  # determinizm

    logs = capsys.readouterr().out
    assert "Wczoraj" not in logs  # surowy tekst nigdy nie trafia do logów (ADR-0006)


@needs_spacy_model
@pytest.mark.parametrize(
    ("body", "status"),
    [
        ("to nie json", 400),
        ({"text": "   "}, 400),
        ({"text": 123}, 400),
        (["lista"], 400),
        ({"text": "a" * 1001}, 413),
    ],
)
def test_handler_rejects_bad_input(handler_module, body, status):
    assert handler_module.handler(_event(body), None)["statusCode"] == status
