"""Testy kontraktu cech — chronią przed rozjazdem treningu i inference (ADR-0002, ADR-0012)."""

import importlib.util

import numpy as np
import pytest

from detector_features import (
    DEFAULT_SPACY_MODEL,
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    N_FEATURES,
    extract,
    extract_many,
    load_nlp,
)

HAS_MODEL = importlib.util.find_spec(DEFAULT_SPACY_MODEL) is not None
needs_model = pytest.mark.skipif(not HAS_MODEL, reason=f"brak modelu {DEFAULT_SPACY_MODEL}")

SAMPLE = (
    "Wczoraj wieczorem poszedłem do kina. Film był długi, ale bardzo ciekawy i dobrze zagrany. "
    "Po seansie rozmawialiśmy o nim jeszcze przez godzinę, siedząc w małej kawiarni na rogu ulicy. "
) * 5


@pytest.fixture(scope="session")
def nlp():
    return load_nlp()


# --- schemat (bez modelu spaCy) ---


def test_schema_has_38_unique_features():
    assert N_FEATURES == 38
    assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES))


def test_schema_order_is_fixed():
    # Kolejność jest częścią kontraktu z wytrenowanym modelem — zmiana wymaga nowej wersji schematu.
    assert FEATURE_NAMES[0] == "Token_Count"
    assert FEATURE_NAMES[12] == "MTLD"
    assert FEATURE_NAMES[18] == "Zipf_MAPE"
    assert FEATURE_NAMES[24] == "Taylor_b"
    assert FEATURE_NAMES[-1] == "MSE_Entropy_Variance"


def test_schema_version_and_model():
    assert FEATURE_SCHEMA_VERSION == "2"
    assert DEFAULT_SPACY_MODEL == "pl_core_news_md"


# --- ekstrakcja (wymaga modelu spaCy) ---


@needs_model
def test_extract_returns_38_finite_floats(nlp):
    vec = extract(SAMPLE, nlp)
    assert vec.shape == (N_FEATURES,)
    assert vec.dtype == np.float64
    assert np.all(np.isfinite(vec))


@needs_model
def test_extract_is_deterministic(nlp):
    # Stałe ziarno szumu w NVG (AGENTS.md, zasada 7).
    assert np.array_equal(extract(SAMPLE, nlp), extract(SAMPLE, nlp))


@needs_model
def test_extract_many_matches_extract(nlp):
    texts = [SAMPLE, "Ala ma kota. Ala ma psa."]
    batch = extract_many(texts, nlp)
    assert batch.shape == (2, N_FEATURES)
    for row, text in zip(batch, texts):
        assert np.array_equal(row, extract(text, nlp))


@needs_model
def test_known_shallow_values(nlp):
    vec = dict(zip(FEATURE_NAMES, extract("Ala ma kota. Ala ma psa.", nlp)))
    # Interpunkcja zostaje w tokenach (jak w treningu): ala ma kota . ala ma psa .
    assert vec["Token_Count"] == 8
    assert vec["Char_Length"] == 24
    assert vec["Comma_Ratio"] == pytest.approx(0.0)
    assert vec["Dot_Ratio"] == pytest.approx(2 / 8, rel=1e-4)


@pytest.mark.parametrize("text", ["", "   ", "...", "Tak."])
@needs_model
def test_degenerate_texts_do_not_crash(nlp, text):
    vec = extract(text, nlp)
    assert vec.shape == (N_FEATURES,)
    assert np.all(np.isfinite(vec))


@needs_model
def test_extract_many_empty_input(nlp):
    assert extract_many([], nlp).shape == (0, N_FEATURES)
