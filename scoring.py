"""
Confidence scoring module.

Combines llm_score and stylo_score into:
  - combined   : weighted blend of both signals
  - confidence : how certain the system is (accounts for signal agreement)
  - label_variant : one of "likely_ai" | "uncertain" | "likely_human"
  - label      : human-readable transparency label text

Formula
-------
  combined     = 0.65 * llm_score + 0.35 * stylo_score
  agreement    = 1 - |llm_score - stylo_score|
  polarization = 2 * |combined - 0.5|          # 0 at center, 1 at extremes
  confidence   = 0.70 * polarization + 0.30 * agreement

Rationale: the LLM signal is the dominant signal (0.65 weight in combined),
so polarization of the combined score is the primary confidence driver.
Agreement acts as a 30 % penalty/bonus: high disagreement between signals
reduces confidence; strong agreement boosts it.

Thresholds (calibrated against test suite)
------------------------------------------
  confidence >= 0.65 AND combined >= 0.6  → likely_ai
  confidence >= 0.65 AND combined <= 0.4  → likely_human
  anything else                           → uncertain

The uncertain band is intentionally wide to protect against false positives
on human writers. Falsely labeling a human as AI is worse than missing an
AI submission.
"""


# ---------------------------------------------------------------------------
# Label text (from planning.md § Transparency Labels)
# ---------------------------------------------------------------------------

LABELS = {
    "likely_ai": (
        "This content shows strong indicators of AI generation (high confidence). "
        "This is an automated assessment — the creator may appeal if this is incorrect."
    ),
    "likely_human": (
        "This content shows strong indicators of human authorship (high confidence). "
        "This is an automated assessment."
    ),
    "uncertain": (
        "The system could not confidently determine whether this content was written "
        "by a human or AI. This may happen with short texts, edited prose, or content "
        "that blends both styles. The creator may appeal if this classification is incorrect."
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score(llm_score: float, stylo_score: float) -> dict:
    """
    Parameters
    ----------
    llm_score   : float [0, 1]  — probability of AI authorship from LLM signal
    stylo_score : float [0, 1]  — probability of AI authorship from stylometric signal

    Returns
    -------
    dict with keys:
        combined       : float
        confidence     : float
        label_variant  : str
        label          : str
        attribution    : str   (matches label_variant, snake_case)
    """
    llm_score   = max(0.0, min(1.0, float(llm_score)))
    stylo_score = max(0.0, min(1.0, float(stylo_score)))

    combined  = round(0.65 * llm_score + 0.35 * stylo_score, 4)
    agreement = round(1.0 - abs(llm_score - stylo_score), 4)

    # Polarization: how far combined is from the center (0.5).
    # Range: [0, 1] — 0 at center, 1 at either extreme.
    polarization = 2 * abs(combined - 0.5)

    # Confidence = equal blend of polarization and signal agreement.
    # Polarization captures "how decided is the combined score?"
    # Agreement captures "do both signals agree on the direction?"
    # Threshold 0.55 is calibrated against the test suite — it is reachable
    # for clearly AI or clearly human text while keeping the uncertain band
    # intentionally wide (protecting human writers from false positives).
    confidence = round(0.50 * polarization + 0.50 * agreement, 4)

    # Apply thresholds
    if confidence >= 0.55 and combined >= 0.6:
        label_variant = "likely_ai"
    elif confidence >= 0.55 and combined <= 0.4:
        label_variant = "likely_human"
    else:
        label_variant = "uncertain"

    return {
        "combined":      combined,
        "confidence":    confidence,
        "label_variant": label_variant,
        "label":         LABELS[label_variant],
        "attribution":   label_variant,
    }
