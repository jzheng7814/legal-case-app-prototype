"""
Sentence indexing utilities for agent tools (ephemeral, in-memory only).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


_SENTENCE_CACHE: Dict[Tuple[str, int], List["SentenceSpan"]] = {}
_TOKENIZER = None


@dataclass(frozen=True)
class SentenceSpan:
    sentence_id: int
    start_char: int
    end_char: int
    text: str


def _ensure_tokenizer():
    global _TOKENIZER
    if _TOKENIZER is not None:
        return _TOKENIZER

    try:
        import nltk
        from nltk.data import find
        from nltk.tokenize.punkt import PunktSentenceTokenizer
    except ImportError as exc:
        raise RuntimeError("NLTK is required for sentence tokenization. Install nltk in the environment.") from exc

    try:
        find("tokenizers/punkt")
    except LookupError as exc:
        raise RuntimeError(
            "NLTK punkt model is missing. Please preinstall by running: "
            "python -m nltk.downloader punkt"
        ) from exc

    _TOKENIZER = PunktSentenceTokenizer()
    return _TOKENIZER


def build_sentence_index(case_id: str, doc_id: int, text: str) -> List[SentenceSpan]:
    """
    Build or return cached sentence spans for a document.
    """
    cache_key = (case_id, doc_id)
    cached = _SENTENCE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    tokenizer = _ensure_tokenizer()
    spans = []
    sentence_id = 0
    for start, end in tokenizer.span_tokenize(text):
        sentence_text = text[start:end]
        spans.append(SentenceSpan(sentence_id=sentence_id, start_char=start, end_char=end, text=sentence_text))
        sentence_id += 1

    _SENTENCE_CACHE[cache_key] = spans
    return spans


def get_sentence_count(case_id: str, doc_id: int, text: str) -> int:
    return len(build_sentence_index(case_id, doc_id, text))

