"""Parsowanie tekstu spaCy do struktury, z której liczone są cechy.

Przeniesione z ai-text-recognition/src/preprocessing/tokenizer.py (SpacyTokenizer) z ustawieniami
używanymi w treningu: bez lematyzacji, bez usuwania stop-words i interpunkcji, lowercase.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import spacy
from spacy.language import Language
from spacy.tokens import Doc

from .schema import DEFAULT_SPACY_MODEL

# Komponenty niepotrzebne do cech — wyłączone dla szybkości (jak w treningu).
DISABLED_COMPONENTS = ("ner", "textcat")


@dataclass(frozen=True)
class ParsedDoc:
    tokens: list[str] = field(default_factory=list)
    pos: list[str] = field(default_factory=list)
    cases: list[str] = field(default_factory=list)
    depths: list[int] = field(default_factory=list)
    raw_char_len: int = 0
    comma_count: int = 0
    dot_count: int = 0
    sent_lengths: list[int] = field(default_factory=list)  # długości zdań w ZNAKACH (jak w oryginale)


def load_nlp(model_name: str = DEFAULT_SPACY_MODEL) -> Language:
    """Ładuje model spaCy. Wołać raz na proces (faza init Lambdy / start workera)."""
    return spacy.load(model_name, disable=list(DISABLED_COMPONENTS))


def _depth(token) -> int:
    depth = 0
    curr = token
    visited = set()
    while curr.head != curr and curr not in visited:
        visited.add(curr)
        depth += 1
        curr = curr.head
    return depth


def parse_doc(doc: Doc, *, use_lemma: bool = False, lowercase: bool = True) -> ParsedDoc:
    tokens: list[str] = []
    pos: list[str] = []
    depths: list[int] = []
    cases: list[str] = []

    for token in doc:
        if token.is_space:
            continue

        text = token.lemma_ if use_lemma else token.text
        if lowercase:
            text = text.lower()
        if text.strip() == "":
            continue

        tokens.append(text)
        pos.append(token.pos_)
        depths.append(_depth(token))
        case = token.morph.get("Case")
        cases.append(case[0] if case else token.pos_)

    return ParsedDoc(
        tokens=tokens,
        pos=pos,
        cases=cases,
        depths=depths,
        raw_char_len=len(doc.text),
        comma_count=doc.text.count(","),
        dot_count=doc.text.count("."),
        sent_lengths=[len(sent.text) for sent in doc.sents],
    )
