"""Trening klasyfikatora XGBoost i eksport kompletnego artefaktu modelu (ADR-0002, ADR-0007, ADR-0012).

Cechy liczone WYŁĄCZNIE przez pakiet `detector_features` (AGENTS.md, zasada 1).

Przykład (z katalogu głównego repo):
    python pipelines/retraining/train.py \
        --data  "<ścieżka>/2025-smigiel/data/train/data.tsv" \
        --labels "<ścieżka>/2025-smigiel/data/train/labels.tsv" \
        --out artifacts/model-v1

Wynik w --out:
    model.ubj             — model XGBoost (format binarny UBJSON, natywny dla xgboost)
    feature_profile.json  — percentyle cech na zbiorze treningowym (flaga OOD — ADR-0007)
    metadata.json         — schemat cech, wersje, hiperparametry, metryki, ranking SHAP cech, hashe danych
    checksums.json        — SHA-256 powyższych plików (weryfikacja w Lambdzie — ADR-0012)
    features.csv          — cechy policzone dla wszystkich próbek (cache; NIE wysyłać do S3 z modelem)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import spacy
import xgboost as xgb
from sklearn.metrics import accuracy_score, f1_score, matthews_corrcoef, roc_auc_score
from sklearn.model_selection import train_test_split

import detector_features
from detector_features import (
    DEFAULT_SPACY_MODEL,
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    N_FEATURES,
    features_from_parsed,
    load_nlp,
    parse_doc,
)

# Najlepsze hiperparametry z ai-text-recognition/src/models/config.py (Optuna).
XGB_PARAMS = {
    "n_estimators": 898,
    "learning_rate": 0.015734269405203786,
    "max_depth": 15,
    "min_child_weight": 7,
    "subsample": 0.7894939253356722,
    "colsample_bytree": 0.9828748511411806,
    "gamma": 0,
    "reg_lambda": 9.924784197985092,
    "reg_alpha": 0,
    "random_state": 42,
    "n_jobs": -1,
}

PROFILE_PERCENTILES = (1, 5, 25, 50, 75, 95, 99)
SHAP_MAX_SAMPLES = 5000  # globalny ranking SHAP liczony na próbce holdoutu (koszt ~ liniowy z liczbą wierszy)


# ---------- dane wejściowe (zgodnie z ai-text-recognition/src/utils/load_data.py) ----------


def _read_tsv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t", header=None, quoting=csv.QUOTE_NONE, low_memory=False)


def load_texts(path: Path) -> list[str]:
    df = _read_tsv(path)
    text_col = df.astype(str).map(len).mean().idxmax()  # kolumna z najdłuższymi wartościami = tekst
    col = df[text_col]
    if str(col.iloc[0]).lower() in {"text", "content", "sentence", "tweet", "id"}:
        col = col.iloc[1:]
    return col.astype(str).tolist()


def load_labels(path: Path) -> list[int]:
    col = _read_tsv(path).iloc[:, -1]
    if isinstance(col.iloc[0], str) and not str(col.iloc[0]).replace(".", "", 1).isdigit():
        col = col.iloc[1:]
    return col.astype(int).tolist()


# ---------- pomocnicze ----------


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def extract_with_progress(texts: list[str], model_name: str, batch_size: int, n_process: int) -> np.ndarray:
    nlp = load_nlp(model_name)
    rows = []
    started = time.perf_counter()
    for i, doc in enumerate(nlp.pipe(texts, batch_size=batch_size, n_process=n_process), start=1):
        rows.append(features_from_parsed(parse_doc(doc)))
        if i % 500 == 0 or i == len(texts):
            elapsed = time.perf_counter() - started
            print(f"  cechy: {i}/{len(texts)}  ({elapsed:.0f} s, {i / elapsed:.1f} tekstów/s)", flush=True)
    return np.vstack(rows) if rows else np.empty((0, N_FEATURES))


def save_features_csv(path: Path, X: np.ndarray, y: np.ndarray) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([*FEATURE_NAMES, "label"])
        for row, label in zip(X, y):
            writer.writerow([*row.tolist(), int(label)])


def load_features_csv(path: Path) -> tuple[np.ndarray, np.ndarray]:
    df = pd.read_csv(path)
    expected = [*FEATURE_NAMES, "label"]
    if list(df.columns) != expected:
        raise SystemExit(
            f"Cache cech {path} ma inne kolumny niż bieżący schemat v{FEATURE_SCHEMA_VERSION} — usuń plik i policz cechy ponownie."
        )
    return df[list(FEATURE_NAMES)].to_numpy(dtype=np.float64), df["label"].to_numpy(dtype=int)


def feature_profile(X: np.ndarray) -> dict:
    profile = {}
    for j, name in enumerate(FEATURE_NAMES):
        col = X[:, j]
        profile[name] = {
            **{f"p{p}": float(np.percentile(col, p)) for p in PROFILE_PERCENTILES},
            "min": float(col.min()),
            "max": float(col.max()),
            "mean": float(col.mean()),
            "std": float(col.std()),
        }
    return {"schema_version": FEATURE_SCHEMA_VERSION, "n_samples": int(X.shape[0]), "features": profile}


def shap_importance(model: xgb.XGBClassifier, X: np.ndarray, seed: int) -> dict:
    """Globalna ważność cech = średnie |SHAP| na holdoucie (ADR-0007, ADR-0016).

    Lambda używa `ranking` do flagi OOD (najważniejsze cechy); `mean_abs_shap` — do raportów w panelu admina.
    """
    if len(X) > SHAP_MAX_SAMPLES:
        X = X[np.random.default_rng(seed).choice(len(X), SHAP_MAX_SAMPLES, replace=False)]
    contribs = model.get_booster().predict(xgb.DMatrix(X), pred_contribs=True)[:, :-1]  # bez kolumny bias
    mean_abs = np.abs(contribs).mean(axis=0)
    order = np.argsort(-mean_abs, kind="stable")
    return {
        "method": "mean_abs_shap",
        "dataset": "holdout",
        "n_samples": int(len(X)),
        "ranking": [FEATURE_NAMES[i] for i in order],
        "mean_abs_shap": {FEATURE_NAMES[i]: float(mean_abs[i]) for i in order},
    }


def evaluate(model: xgb.XGBClassifier, X: np.ndarray, y: np.ndarray) -> dict:
    proba = model.predict_proba(X)[:, 1]
    pred = (proba >= 0.5).astype(int)
    return {
        "accuracy": float(accuracy_score(y, pred)),
        "f1_macro": float(f1_score(y, pred, average="macro")),
        "mcc": float(matthews_corrcoef(y, pred)),
        "roc_auc": float(roc_auc_score(y, proba)),
        "n": int(len(y)),
    }


# ---------- główny przebieg ----------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, required=True, help="data.tsv z tekstami")
    parser.add_argument("--labels", type=Path, required=True, help="labels.tsv z etykietami (0/1)")
    parser.add_argument("--out", type=Path, required=True, help="katalog wyjściowy artefaktu")
    parser.add_argument("--spacy-model", default=DEFAULT_SPACY_MODEL)
    parser.add_argument("--test-size", type=float, default=0.2, help="udział zbioru holdout do metryk")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--n-process", type=int, default=1, help="równoległość spaCy (nlp.pipe)")
    parser.add_argument("--limit", type=int, default=None, help="tylko pierwsze N próbek (szybki test)")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    features_path = args.out / "features.csv"

    texts, labels = load_texts(args.data), load_labels(args.labels)
    if len(texts) != len(labels):
        raise SystemExit(f"Liczba tekstów ({len(texts)}) różni się od liczby etykiet ({len(labels)}).")
    if args.limit:
        texts, labels = texts[: args.limit], labels[: args.limit]
    y_all = np.asarray(labels, dtype=int)
    classes, counts = np.unique(y_all, return_counts=True)
    print(f"Dane: {len(texts)} próbek, klasy: {dict(zip(classes.tolist(), counts.tolist()))}")

    if features_path.exists():
        print(f"Używam cache cech: {features_path}")
        X_all, y_cached = load_features_csv(features_path)
        if not np.array_equal(y_cached, y_all):
            raise SystemExit("Cache cech nie pasuje do etykiet — usuń features.csv i policz cechy ponownie.")
    else:
        print(f"Liczenie {N_FEATURES} cech (schemat v{FEATURE_SCHEMA_VERSION}, model {args.spacy_model})...")
        X_all = extract_with_progress(texts, args.spacy_model, args.batch_size, args.n_process)
        save_features_csv(features_path, X_all, y_all)

    X_train, X_test, y_train, y_test = train_test_split(
        X_all, y_all, test_size=args.test_size, stratify=y_all, random_state=args.seed
    )

    print(f"Trening XGBoost: {len(y_train)} próbek treningowych, {len(y_test)} holdout...")
    params = {**XGB_PARAMS, "random_state": args.seed}
    model = xgb.XGBClassifier(**params)
    model.fit(X_train, y_train)

    metrics = {"holdout": evaluate(model, X_test, y_test), "train": evaluate(model, X_train, y_train)}
    print(json.dumps(metrics["holdout"], indent=2))

    print("Ranking ważności cech (średnie |SHAP| na holdoucie)...")
    importance = shap_importance(model, X_test, args.seed)
    print("  top 5:", ", ".join(importance["ranking"][:5]))

    model_path = args.out / "model.ubj"
    model.save_model(model_path)

    profile_path = args.out / "feature_profile.json"
    profile_path.write_text(json.dumps(feature_profile(X_train), indent=2), encoding="utf-8")

    nlp_meta = spacy.load(args.spacy_model).meta  # tylko metadane modelu
    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": list(FEATURE_NAMES),
        "detector_features_version": detector_features.__version__,
        "spacy": {"version": spacy.__version__, "model": args.spacy_model, "model_version": nlp_meta.get("version")},
        "xgboost_version": xgb.__version__,
        "python_version": platform.python_version(),
        "model_format": "xgboost-ubj",
        "decision_threshold": 0.5,
        "label_meaning": {"0": "human", "1": "ai"},
        "hyperparameters": params,
        "split": {"test_size": args.test_size, "seed": args.seed, "stratified": True},
        "metrics": metrics,
        "feature_importance": importance,
        "data": {
            "n_samples": int(len(y_all)),
            "data_sha256": sha256_file(args.data),
            "labels_sha256": sha256_file(args.labels),
            "limit": args.limit,
        },
    }
    metadata_path = args.out / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    checksums = {p.name: sha256_file(p) for p in (model_path, profile_path, metadata_path)}
    (args.out / "checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")

    print(f"Artefakt zapisany w {args.out.resolve()}")
    print("Do S3 (ADR-0012) wysyłamy: model.ubj, feature_profile.json, metadata.json, checksums.json.")


if __name__ == "__main__":
    sys.exit(main())
