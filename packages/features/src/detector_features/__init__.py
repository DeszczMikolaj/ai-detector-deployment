"""detector_features — jedyne źródło ekstrakcji cech dla treningu i inference (AGENTS.md, zasada 1).

Użycie:
    from detector_features import load_nlp, extract, extract_many, FEATURE_NAMES

    nlp = load_nlp()                  # raz na proces
    vec = extract("Jakiś tekst.", nlp)  # np.ndarray o kształcie (38,)
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from spacy.language import Language

from .dynamics import dynamics_features
from .parsing import ParsedDoc, load_nlp, parse_doc
from .schema import DEFAULT_SPACY_MODEL, FEATURE_NAMES, FEATURE_SCHEMA_VERSION, N_FEATURES
from .stylometry import shallow_features
from .zipf import zipf_features

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_SPACY_MODEL",
    "FEATURE_NAMES",
    "FEATURE_SCHEMA_VERSION",
    "N_FEATURES",
    "ParsedDoc",
    "extract",
    "extract_many",
    "features_from_parsed",
    "load_nlp",
    "parse_doc",
]


def features_from_parsed(doc: ParsedDoc) -> np.ndarray:
    """38 cech w kolejności FEATURE_NAMES. NaN/inf zamieniane na 0 (jak SafeFeatures w oryginale)."""
    values = shallow_features(doc) + zipf_features(doc) + dynamics_features(doc)
    if len(values) != N_FEATURES:  # ochrona kontraktu — nigdy nie powinno wystąpić
        raise RuntimeError(f"Oczekiwano {N_FEATURES} cech, otrzymano {len(values)}")
    arr = np.asarray(values, dtype=np.float64)
    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)


def extract(text: str, nlp: Language) -> np.ndarray:
    """Cechy dla jednego tekstu (inference)."""
    return features_from_parsed(parse_doc(nlp(text)))


def extract_many(texts: Iterable[str], nlp: Language, batch_size: int = 100) -> np.ndarray:
    """Cechy dla wielu tekstów (trening) — macierz (n, 38). Używa nlp.pipe dla wydajności."""
    rows = [features_from_parsed(parse_doc(doc)) for doc in nlp.pipe(texts, batch_size=batch_size)]
    if not rows:
        return np.empty((0, N_FEATURES), dtype=np.float64)
    return np.vstack(rows)
