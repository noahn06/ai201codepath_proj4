"""
Signal 2 — Stylometric Analyzer (pure Python, no external libraries).

Computes four structural statistics and combines them into a single
`stylo_score` float in [0, 1], where 1.0 means AI-like and 0.0 means
human-like.

Sub-measures
------------
1. Sentence-length variance  — low variance → AI-like
2. Type-token ratio (TTR)    — normalized for text length; low TTR → AI-like
3. Punctuation density       — sparse punctuation → AI-like
4. Average sentence length   — close to AI "sweet spot" of ~18 words → AI-like

Each sub-measure returns a partial score in [0, 1] where a *higher* value
means *more AI-like*.  The four partial scores are averaged into the final
`stylo_score`.
"""

import re
import math
import statistics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on . ! ? boundaries (handles lowercase follows)."""
    # Split whenever . ! ? is followed by whitespace (regardless of case),
    # or at end of string.  This handles informal writing where sentences
    # don't start with uppercase.
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    # Further split on newlines in case paragraphs are passed in.
    sentences = []
    for part in parts:
        for line in part.splitlines():
            line = line.strip()
            if line:
                sentences.append(line)
    return sentences


def _tokenize_words(text: str) -> list[str]:
    """Return a list of lowercase alphabetic tokens (no apostrophes)."""
    return re.findall(r"[a-zA-Z]+", text.lower())


# ---------------------------------------------------------------------------
# Sub-measure 1: Sentence-length variance
#
# AI text tends to produce sentences of similar length, so variance is low.
# Low variance → score near 1 (AI-like).
# High variance → score near 0 (human-like).
# ---------------------------------------------------------------------------

def _sentence_length_variance_score(sentences: list[str]) -> float:
    if len(sentences) < 2:
        # Can't compute meaningful variance — default to neutral
        return 0.5

    lengths = [len(s.split()) for s in sentences]

    try:
        var = statistics.variance(lengths)
    except statistics.StatisticsError:
        return 0.5

    # Empirically:
    #   AI prose:    variance ~3–30  (uniform, controlled sentence lengths)
    #   Human prose: variance ~30–200 (erratic mix of short and long sentences)
    #
    # Logistic curve centred at var=30, scale=12:
    #   var=0  → score ≈ 0.92 (AI-like)
    #   var=30 → score ≈ 0.50 (neutral)
    #   var=80 → score ≈ 0.02 (human-like)
    score = 1.0 / (1.0 + math.exp((var - 30) / 12))
    return round(max(0.0, min(1.0, score)), 4)


# ---------------------------------------------------------------------------
# Sub-measure 2: Type-token ratio (TTR) — length-corrected
#
# Raw TTR is unreliable on short texts because even random text has very high
# TTR when short.  We use a length-penalty:
#   adj_ttr = raw_ttr / (1 + log(n_words / 30)) for n_words > 30
#           = raw_ttr                            for n_words <= 30
#
# AI text at longer lengths tends to repeat key terms more often (lower TTR).
# Human writing is more varied.
# Low adj_ttr → AI-like → score near 1.
# ---------------------------------------------------------------------------

def _ttr_score(words: list[str]) -> float:
    n = len(words)
    if n < 10:
        return 0.5   # not enough data

    raw_ttr = len(set(words)) / n

    # Length-correct: longer texts naturally have lower TTR; we reward that
    # length effect for AI text by applying a modest penalty based on length.
    if n > 30:
        adj_ttr = raw_ttr / (1 + math.log(n / 30) * 0.15)
    else:
        adj_ttr = raw_ttr

    # Score mapping:
    #   adj_ttr <= 0.50 → 1.0 (AI-like, low vocab diversity)
    #   adj_ttr >= 0.85 → 0.0 (human-like, high vocab diversity)
    score = (0.85 - adj_ttr) / (0.85 - 0.50)
    return round(max(0.0, min(1.0, score)), 4)


# ---------------------------------------------------------------------------
# Sub-measure 3: Punctuation density
#
# We look at the ratio of punctuation characters to word characters.
# Human writing uses commas, question marks, dashes, etc. more variably.
# AI text tends toward clean, minimal punctuation (mainly periods and commas).
#
# We measure punctuation-to-word ratio rather than punctuation-to-all-chars
# to avoid penalising texts with lots of whitespace.
# ---------------------------------------------------------------------------

def _punctuation_density_score(text: str) -> float:
    if not text:
        return 0.5

    # Meaningful punctuation (not sentence-terminal periods — those are neutral)
    expressive_punct = set(",;:!?—–-…()[]\"'")
    n_punct = sum(1 for ch in text if ch in expressive_punct)
    n_alpha = sum(1 for ch in text if ch.isalpha())

    if n_alpha == 0:
        return 0.5

    # Expressive punctuation per 100 alphabetic characters
    rate = 100 * n_punct / n_alpha

    # AI text: rate ~1–4  (sparing, clean)
    # Human casual: rate ~5–15 (lots of ? ! , — etc.)
    # Human formal: rate ~2–6 (moderate)
    #
    # Score mapping:
    #   rate <= 1.5 → 1.0 (very AI-like)
    #   rate >= 7.0 → 0.0 (human-like)
    score = (7.0 - rate) / (7.0 - 1.5)
    return round(max(0.0, min(1.0, score)), 4)


# ---------------------------------------------------------------------------
# Sub-measure 4: Average sentence length
#
# AI text gravitates toward moderate sentence lengths (~15–25 words).
# Human writing has more extremes — very short interjections or very long
# complex sentences.  We score proximity to the AI "sweet spot."
# ---------------------------------------------------------------------------

def _avg_sentence_length_score(sentences: list[str]) -> float:
    if not sentences:
        return 0.5

    lengths = [len(s.split()) for s in sentences]
    avg = sum(lengths) / len(lengths)

    # Distance from the AI sweet-spot of 18 words.
    # dist=0  → score 1.0 (perfectly AI-like)
    # dist=18 → score 0.0 (very far from sweet spot)
    dist = abs(avg - 18)
    score = max(0.0, 1.0 - dist / 18)
    return round(max(0.0, min(1.0, score)), 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze(text: str) -> dict:
    """
    Compute the four stylometric sub-measures and return a dict with:
        - stylo_score : float [0, 1]  — combined score (1 = AI-like)
        - breakdown   : dict          — individual sub-measure scores
    """
    sentences = _split_sentences(text)
    words = _tokenize_words(text)

    sl_var   = _sentence_length_variance_score(sentences)
    ttr      = _ttr_score(words)
    punct    = _punctuation_density_score(text)
    avg_len  = _avg_sentence_length_score(sentences)

    stylo_score = round((sl_var + ttr + punct + avg_len) / 4, 4)

    return {
        "stylo_score": stylo_score,
        "breakdown": {
            "sentence_length_variance": sl_var,
            "type_token_ratio":         ttr,
            "punctuation_density":      punct,
            "avg_sentence_length":      avg_len,
        },
    }
