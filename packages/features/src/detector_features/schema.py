"""Kontrakt cech: nazwy, kolejność i wersja schematu.

Każda zmiana listy, kolejności lub sposobu liczenia którejkolwiek cechy wymaga podniesienia
FEATURE_SCHEMA_VERSION — model wytrenowany na innym schemacie nie może być serwowany (ADR-0012).

Historia:
- "1" — schemat z repo ai-text-recognition: liczono 38 wartości, ale nagłówek CSV miał 37 nazw
  (brak MTLD); pandas robił z Token_Count indeks, a pierwsze 12 kolumn miało nazwy przesunięte o jedną.
- "2" — 38 cech z poprawnymi nazwami (dodane MTLD), deterministyczny szum w NVG, regresja liniowa
  liczona w numpy (bez scikit-learn).
"""

FEATURE_SCHEMA_VERSION = "2"

DEFAULT_SPACY_MODEL = "pl_core_news_md"  # ADR-0015

SHALLOW_FEATURES = (
    "Token_Count",
    "Char_Length",
    "Comma_Ratio",
    "Dot_Ratio",
    "Avg_Sent_Len",
    "Var_Sent_Len",
    "TTR",
    "HLR",
    "Entropy",
    "Avg_Word_Len",
    "Var_Word_Len",
    "Yules_K",
    "MTLD",
    "Noun_Ratio",
    "Verb_Ratio",
    "Adj_Ratio",
    "Avg_Dep_Depth",
    "Max_Dep_Depth",
)

ZIPF_FEATURES = (
    "Zipf_MAPE",
    "Zipf_Correlation",
    "Zipf_Slope",
    "Zipf_Residual_Var",
    "Zipf_KS_Stat",
    "Metric_R",
)

DYNAMICS_FEATURES = (
    "Taylor_b",
    "RQA_Recurrence_Rate",
    "RQA_Determinism",
    "RQA_Entropy",
    "RQA_Laminarity",
    "CRQA_Recurrence_Rate",
    "CRQA_Determinism",
    "CRQA_Entropy",
    "CRQA_Laminarity",
    "NVG_Avg_Degree",
    "NVG_Clustering",
    "NVG_Avg_Path_Length",
    "NVG_Graph_Entropy",
    "MSE_Entropy_Variance",
)

FEATURE_NAMES: tuple[str, ...] = SHALLOW_FEATURES + ZIPF_FEATURES + DYNAMICS_FEATURES
N_FEATURES = len(FEATURE_NAMES)  # 38
