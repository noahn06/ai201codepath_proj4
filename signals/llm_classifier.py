import os
from groq import Groq

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


SYSTEM_PROMPT = """You are an expert at distinguishing human-written text from AI-generated text.
Analyze the text and return ONLY a JSON object with one key: "ai_probability" (a float between 0.0 and 1.0).
0.0 means definitely human-written. 1.0 means definitely AI-generated.
Return nothing else — no explanation, no markdown, just the JSON."""


def classify(text: str) -> float:
    """Returns a float [0, 1] — probability that the text is AI-generated."""
    response = _get_client().chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Text to analyze:\n\n{text}"},
        ],
        temperature=0.0,
        max_tokens=32,
    )
    raw = response.choices[0].message.content.strip()

    # Parse the JSON; fall back to 0.5 if the model misbehaves
    try:
        import json
        data = json.loads(raw)
        score = float(data["ai_probability"])
        return max(0.0, min(1.0, score))
    except Exception:
        # Try a simple float parse if the model returned just a number
        try:
            return max(0.0, min(1.0, float(raw)))
        except Exception:
            return 0.5
