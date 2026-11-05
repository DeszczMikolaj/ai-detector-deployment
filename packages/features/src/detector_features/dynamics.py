"""Dynamika nieliniowa (14 cech). Przeniesione z ai-text-recognition/src/preprocessing/dynamics.py.

Zmiany względem oryginału:
- szum rozbijający remisy w NVG generowany ze stałego ziarna (`NVG_SEED`) — ten sam tekst daje
  zawsze te same cechy (AGENTS.md, zasada 7; schemat cech v2),
- regresja Taylora liczona w numpy zamiast sklearn.LinearRegression (matematycznie to samo).
"""

from __future__ import annotations

from collections import Counter

import networkx as nx
import numpy as np
from ts2vg import NaturalVG

from .parsing import ParsedDoc
from .zipf import _ols

NVG_SEED = 42
MAX_SEQ = 300  # RQA/CRQA/NVG liczone na pierwszych 300 tokenach (ograniczenie kosztu O(N^2))
MSE_WINDOW = 20


def _runs(binary: np.ndarray) -> np.ndarray:
    runs = np.diff(np.concatenate(([0], binary.astype(int), [0])))
    starts, ends = np.where(runs == 1)[0], np.where(runs == -1)[0]
    lengths = ends - starts
    return lengths[lengths >= 2]


def _rqa(matrix: np.ndarray, n: int) -> tuple[float, float, float, float]:
    """Recurrence rate, determinism, entropy of diagonal lines, laminarity."""
    total = np.sum(matrix)
    rr = total / (n * n)

    diag_lengths: list[int] = []
    for offset in range(1, n):
        diag_lengths.extend(_runs(np.diag(matrix, k=offset)))
    det = (sum(diag_lengths) * 2) / total if total > 0 else 0.0

    if diag_lengths:
        p = np.array(list(Counter(diag_lengths).values())) / len(diag_lengths)
        entr = float(-np.sum(p * np.log(p + 1e-12)))
    else:
        entr = 0.0

    vert_lengths: list[int] = []
    for col in range(n):
        vert_lengths.extend(_runs(matrix[:, col]))
    lam = sum(vert_lengths) / total if total > 0 else 0.0

    return float(rr), float(det), entr, float(lam)


def _taylor_b(tokens: list[str]) -> float:
    chunk_size = max(10, len(tokens) // 10)
    chunks = [tokens[i : i + chunk_size] for i in range(0, len(tokens), chunk_size)]
    means, variances = [], []
    for chunk in chunks:
        freqs = list(Counter(chunk).values())
        if len(freqs) > 1:
            means.append(np.mean(freqs))
            variances.append(np.var(freqs))
    means_a, variances_a = np.array(means), np.array(variances)
    valid = (means_a > 0) & (variances_a > 0)
    if np.sum(valid) < 3:
        return 0.0
    try:
        slope, _ = _ols(np.log(means_a[valid]), np.log(variances_a[valid]))
        return slope
    except Exception:
        return 0.0


def _nvg(depths: list[int]) -> tuple[float, float, float, float]:
    seq = depths[:MAX_SEQ]
    n = len(seq)
    if n <= 5:
        return 0.0, 0.0, 0.0, 0.0
    try:
        rng = np.random.default_rng(NVG_SEED)
        y = np.array(seq, dtype=np.float64) + rng.uniform(0, 1e-5, size=n)

        vg = NaturalVG()
        vg.build(y)
        graph = nx.Graph()
        graph.add_nodes_from(range(n))
        graph.add_edges_from(vg.edges)

        degrees = [d for _, d in graph.degree()]
        avg_degree = float(np.mean(degrees)) if degrees else 0.0
        deg_probs = np.array(list(Counter(degrees).values())) / len(degrees)
        graph_entropy = float(-np.sum(deg_probs * np.log(deg_probs + 1e-12)))
        clustering = float(nx.average_clustering(graph))

        components = sorted(nx.connected_components(graph), key=len, reverse=True)
        if components and len(components[0]) > 1:
            avg_path = float(nx.average_shortest_path_length(graph.subgraph(components[0])))
        else:
            avg_path = 0.0
        return avg_degree, clustering, avg_path, graph_entropy
    except Exception:
        return 0.0, 0.0, 0.0, 0.0


def _mse_variance(tokens: list[str]) -> float:
    entropies = []
    for i in range(0, len(tokens), MSE_WINDOW):
        chunk = tokens[i : i + MSE_WINDOW]
        if len(chunk) < 5:
            continue
        p = np.array(list(Counter(chunk).values())) / len(chunk)
        entropies.append(-np.sum(p * np.log(p + 1e-12)))
    return float(np.var(entropies)) if len(entropies) > 1 else 0.0


def dynamics_features(doc: ParsedDoc) -> list[float]:
    tokens, cases, depths = doc.tokens, doc.cases, doc.depths
    if len(tokens) < 10:
        return [0.0] * 14

    taylor_b = _taylor_b(tokens)

    seq_cases = cases[:MAX_SEQ]
    seq_lens = [len(t) for t in tokens[:MAX_SEQ]]
    n_cases = len(seq_cases)
    if n_cases > 5:
        r_cases = np.equal.outer(seq_cases, seq_cases)
        r_lens = np.equal.outer(seq_lens, seq_lens)
        joint = r_cases & r_lens
        np.fill_diagonal(r_cases, False)
        np.fill_diagonal(joint, False)
        rqa = _rqa(r_cases, n_cases)
        crqa = _rqa(joint, n_cases)
    else:
        rqa = crqa = (0.0, 0.0, 0.0, 0.0)

    nvg = _nvg(depths)
    mse_var = _mse_variance(tokens)

    return [taylor_b, *rqa, *crqa, *nvg, mse_var]
