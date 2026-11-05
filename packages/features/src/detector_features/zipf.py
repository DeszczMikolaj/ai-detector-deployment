"""Błędy względem prawa Zipfa (6 cech). Przeniesione z ai-text-recognition/src/preprocessing/zipf.py.

Zmiana względem oryginału: regresja liniowa liczona w numpy (`_ols`) zamiast sklearn.LinearRegression —
matematycznie to samo (OLS z wyrazem wolnym), bez ciężkiej zależności w obrazie Lambdy.
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from .parsing import ParsedDoc

_EMPTY = [0.0, 0.0, -1.0, 0.0, 0.0, 0.0]


def _ols(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Zwraca (slope, intercept) regresji y = slope * x + intercept metodą najmniejszych kwadratów."""
    x_mean, y_mean = x.mean(), y.mean()
    denom = np.sum((x - x_mean) ** 2)
    slope = float(np.sum((x - x_mean) * (y - y_mean)) / denom) if denom > 0 else 0.0
    return slope, float(y_mean - slope * x_mean)


def zipf_features(doc: ParsedDoc) -> list[float]:
    tokens = doc.tokens
    if len(tokens) < 3:
        return list(_EMPTY)

    counts = Counter(tokens)
    freqs = np.array(sorted(counts.values(), reverse=True), dtype=np.float64)
    ranks = np.arange(1, len(freqs) + 1, dtype=np.float64)
    log_r, log_f = np.log(ranks), np.log(freqs)

    if len(log_r) < 2 or np.std(log_f) == 0:
        return list(_EMPTY)

    slope, intercept = _ols(log_r, log_f)
    pred = slope * log_r + intercept

    mape = float(np.mean(np.abs((np.exp(log_f) - np.exp(pred)) / np.maximum(np.exp(log_f), 1))))
    corr = float(np.corrcoef(log_f, pred)[0, 1])
    if np.isnan(corr):
        corr = 0.0
    res_var = float(np.var(log_f - pred))

    emp_pdf = freqs / np.sum(freqs)
    fit_pdf = np.exp(pred) / np.sum(np.exp(pred))
    ks_stat = float(np.max(np.abs(np.cumsum(emp_pdf) - np.cumsum(fit_pdf))))

    # Metric R (proxy prawa Heapsa)
    half = len(tokens) // 2
    second = set(tokens[half:])
    metric_r = len(second - set(tokens[:half])) / (len(second) + 1e-8)

    return [mape, corr, slope, res_var, ks_stat, metric_r]
