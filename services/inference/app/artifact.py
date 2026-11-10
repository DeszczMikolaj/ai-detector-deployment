"""Artefakt modelu championa: pobranie z S3, weryfikacja i załadowanie (ADR-0007, ADR-0012).

Format artefaktu tworzy `pipelines/retraining/train.py`:
    model.ubj             model XGBoost (binary:logistic)
    feature_profile.json  percentyle cech na zbiorze treningowym (flaga OOD)
    metadata.json         wersja schematu cech, lista cech, wersje spaCy/xgboost, próg decyzji
    checksums.json        SHA-256 trzech plików powyżej

Każda niezgodność kończy się wyjątkiem `ArtifactError`. W Lambdzie oznacza to błąd fazy init,
więc wersja z niepoprawnym modelem nie przyjmie ruchu (ADR-0012, pkt 3).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import xgboost as xgb

from detector_features import FEATURE_NAMES, FEATURE_SCHEMA_VERSION

CHECKSUMS_FILE = "checksums.json"
ARTIFACT_FILES = ("model.ubj", "feature_profile.json", "metadata.json")

# Flaga OOD (ADR-0007): poza p1–p99 treningu jest >= OOD_MIN_FEATURES dowolnych cech
# albo co najmniej jedna z OOD_TOP_K najważniejszych cech modelu.
OOD_LOW, OOD_HIGH = "p1", "p99"
OOD_MIN_FEATURES = int(os.environ.get("OOD_MIN_FEATURES", "3"))
OOD_TOP_K = int(os.environ.get("OOD_TOP_K", "5"))


class ArtifactError(RuntimeError):
    """Artefakt jest niekompletny, uszkodzony albo niezgodny z kodem inference."""


# ---------- pobranie ----------


def fetch(uri: str, workdir: Path, s3_client=None) -> Path:
    """Zwraca katalog z plikami artefaktu.

    `s3://bucket/prefix/` — pobiera pliki do `workdir` (w Lambdzie: /tmp).
    Ścieżka lokalna — używa jej bez kopiowania (testy, uruchomienie lokalne).
    """
    if not uri.startswith("s3://"):
        path = Path(uri)
        if not path.is_dir():
            raise ArtifactError(f"Katalog artefaktu nie istnieje: {uri}")
        return path

    parsed = urlparse(uri)
    bucket, prefix = parsed.netloc, parsed.path.lstrip("/")
    if not bucket or not prefix:
        raise ArtifactError(f"Niepoprawny MODEL_URI: {uri}")
    prefix = prefix if prefix.endswith("/") else prefix + "/"

    if s3_client is None:
        import boto3  # jest w obrazie bazowym Lambdy

        s3_client = boto3.client("s3")

    workdir.mkdir(parents=True, exist_ok=True)
    # Pobieramy tylko znane nazwy plików — nic z S3 nie decyduje o ścieżkach zapisu.
    for name in (CHECKSUMS_FILE, *ARTIFACT_FILES):
        s3_client.download_file(bucket, prefix + name, str(workdir / name))
    return workdir


# ---------- weryfikacja ----------


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_checksums(directory: Path) -> None:
    try:
        expected = json.loads((directory / CHECKSUMS_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"Brak lub błędny {CHECKSUMS_FILE}: {exc}") from exc

    if set(expected) != set(ARTIFACT_FILES):
        raise ArtifactError(f"{CHECKSUMS_FILE} musi opisywać dokładnie {list(ARTIFACT_FILES)}, jest {sorted(expected)}")

    for name in ARTIFACT_FILES:
        path = directory / name
        if not path.is_file():
            raise ArtifactError(f"Brak pliku artefaktu: {name}")
        if _sha256(path) != expected[name]:
            raise ArtifactError(f"Suma SHA-256 pliku {name} nie zgadza się z {CHECKSUMS_FILE}")


def verify_compatibility(metadata: dict, profile: dict, spacy_model: str, spacy_model_version: str) -> None:
    """Model musi pasować do kodu cech i modelu spaCy w obrazie (train/serve skew — ADR-0002)."""
    if str(metadata.get("feature_schema_version")) != FEATURE_SCHEMA_VERSION:
        raise ArtifactError(
            f"Schemat cech modelu v{metadata.get('feature_schema_version')} ≠ v{FEATURE_SCHEMA_VERSION} w obrazie"
        )
    if list(metadata.get("feature_names", [])) != list(FEATURE_NAMES):
        raise ArtifactError("Lista lub kolejność cech w metadata.json różni się od detector_features")
    if str(profile.get("schema_version")) != FEATURE_SCHEMA_VERSION:
        raise ArtifactError("Profil cech ma inną wersję schematu niż obraz")
    if set(profile.get("features", {})) != set(FEATURE_NAMES):
        raise ArtifactError("Profil cech nie opisuje wszystkich cech schematu")

    spacy_meta = metadata.get("spacy", {})
    if spacy_meta.get("model") != spacy_model or spacy_meta.get("model_version") != spacy_model_version:
        raise ArtifactError(
            f"Model trenowano na {spacy_meta.get('model')} {spacy_meta.get('model_version')}, "
            f"a obraz ma {spacy_model} {spacy_model_version}"
        )


# ---------- model ----------


def _top_feature_indices(booster: xgb.Booster, k: int) -> tuple[int, ...]:
    """Najważniejsze cechy wg total_gain modelu.

    ADR-0007 mówi o ważności wg SHAP; total_gain to przybliżenie liczone z samego modelu, bez danych
    treningowych. Gdy train.py zacznie zapisywać ranking SHAP w metadata.json, zastąpić tę funkcję.
    """
    scores = booster.get_score(importance_type="total_gain")
    index = {name: i for i, name in enumerate(FEATURE_NAMES)}

    def to_index(key: str) -> int:
        return index[key] if key in index else int(key.removeprefix("f"))

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return tuple(to_index(key) for key, _ in ranked[:k])


@dataclass(frozen=True)
class Prediction:
    ai_probability: float
    label: str
    out_of_distribution: bool
    ood_features: tuple[str, ...]


@dataclass(frozen=True)
class ModelArtifact:
    version: str
    booster: xgb.Booster
    metadata: dict
    threshold: float
    labels: dict[int, str]
    low: np.ndarray
    high: np.ndarray
    top_features: tuple[int, ...]

    def predict(self, features: np.ndarray) -> Prediction:
        x = np.asarray(features, dtype=np.float64).reshape(1, -1)
        proba = float(self.booster.inplace_predict(x)[0])  # binary:logistic → prawdopodobieństwo klasy 1

        outside = np.flatnonzero((x[0] < self.low) | (x[0] > self.high))
        flag = len(outside) >= OOD_MIN_FEATURES or any(i in self.top_features for i in outside)

        return Prediction(
            ai_probability=proba,
            label=self.labels[int(proba >= self.threshold)],
            out_of_distribution=bool(flag),
            ood_features=tuple(FEATURE_NAMES[i] for i in outside),
        )


def version_from_uri(uri: str) -> str:
    """`s3://bucket/models/v1/` → `v1`."""
    return uri.rstrip("/").rsplit("/", 1)[-1]


def load(uri: str, *, spacy_model: str, spacy_model_version: str, workdir: Path = Path("/tmp/model"), s3_client=None) -> ModelArtifact:
    directory = fetch(uri, workdir, s3_client)
    verify_checksums(directory)

    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    profile = json.loads((directory / "feature_profile.json").read_text(encoding="utf-8"))
    verify_compatibility(metadata, profile, spacy_model, spacy_model_version)

    booster = xgb.Booster()
    booster.load_model(directory / "model.ubj")
    booster.set_param({"nthread": 1})  # jedno zapytanie = jeden wiersz; wątki tylko dodają narzut
    if booster.num_features() != len(FEATURE_NAMES):
        raise ArtifactError(f"Model oczekuje {booster.num_features()} cech, schemat ma {len(FEATURE_NAMES)}")

    features = profile["features"]
    labels = {int(k): v for k, v in metadata.get("label_meaning", {"0": "human", "1": "ai"}).items()}

    return ModelArtifact(
        version=version_from_uri(uri),
        booster=booster,
        metadata=metadata,
        threshold=float(metadata.get("decision_threshold", 0.5)),
        labels=labels,
        low=np.array([features[name][OOD_LOW] for name in FEATURE_NAMES]),
        high=np.array([features[name][OOD_HIGH] for name in FEATURE_NAMES]),
        top_features=_top_feature_indices(booster, OOD_TOP_K),
    )
