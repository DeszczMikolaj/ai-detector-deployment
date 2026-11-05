"""Płytka stylometria (18 cech). Przeniesione z ai-text-recognition/src/preprocessing/stylometry.py bez zmian logiki."""

from __future__ import annotations

from collections import Counter

import numpy as np

from .parsing import ParsedDoc


def calc_mtld(tokens: list[str], ttr_threshold: float = 0.72) -> float:
    """Measure of Textual Lexical Diversity — liczona od przodu i od tyłu, uśredniona."""
    if not tokens:
        return 0.0

    def evaluate(seq):
        factors, ttr, token_count = 0, 1.0, 0
        types = set()
        for token in seq:
            token_count += 1
            types.add(token)
            ttr = len(types) / token_count
            if ttr < ttr_threshold:
                factors += 1
                types, ttr, token_count = set(), 1.0, 0
        if token_count > 0:
            factors += (1.0 - ttr) / (1.0 - ttr_threshold)
        return len(seq) / factors if factors > 0 else 0.0

    return (evaluate(tokens) + evaluate(tokens[::-1])) / 2.0


def shallow_features(doc: ParsedDoc) -> list[float]:
    tokens, pos_tags, depths = doc.tokens, doc.pos, doc.depths
    n = len(tokens)

    raw_len = doc.raw_char_len
    comma_ratio = doc.comma_count / (n + 1e-5)
    dot_ratio = doc.dot_count / (n + 1e-5)
    sent_lengths = doc.sent_lengths
    avg_sent_len = float(np.mean(sent_lengths)) if sent_lengths else 0.0
    var_sent_len = float(np.var(sent_lengths)) if sent_lengths else 0.0

    if n == 0:
        return [n, raw_len, comma_ratio, dot_ratio, avg_sent_len, var_sent_len] + [0.0] * 12

    counts = Counter(tokens)
    ttr = len(counts) / n
    hlr = sum(1 for c in counts.values() if c == 1) / n
    probs = np.array(list(counts.values())) / n
    entropy = float(-np.sum(probs * np.log(probs + 1e-12)))

    word_lengths = np.array([len(t) for t in tokens])
    avg_word_len, var_word_len = float(np.mean(word_lengths)), float(np.var(word_lengths))

    m1, m2 = n, sum(c**2 for c in counts.values())
    yules_k = 10000 * (m2 - m1) / (m1**2) if m1 > 1 else 0.0

    mtld = calc_mtld(tokens)

    pos_counts = Counter(pos_tags)
    noun_ratio = pos_counts.get("NOUN", 0) / n
    verb_ratio = pos_counts.get("VERB", 0) / n
    adj_ratio = pos_counts.get("ADJ", 0) / n
    if depths:
        avg_dep_depth, max_dep_depth = float(np.mean(depths)), float(np.max(depths))
    else:
        avg_dep_depth, max_dep_depth = 0.0, 0.0

    return [
        n, raw_len, comma_ratio, dot_ratio, avg_sent_len, var_sent_len,
        ttr, hlr, entropy, avg_word_len, var_word_len,
        yules_k, mtld,
        noun_ratio, verb_ratio, adj_ratio, avg_dep_depth, max_dep_depth,
    ]
