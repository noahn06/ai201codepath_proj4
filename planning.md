# provenance guard — planning

---

## Architecture

text submitted → rate limiter → llm classifier + stylometric analyzer → confidence scorer → label → audit log → response

appeal submitted → rate limiter → appeal handler → audit log → response

when a submission comes in, it passes through the rate limiter first so the server doesn't get spammed. then it runs through both detection signals at the same time. their scores go into the confidence scorer, which returns a combined score and a confidence level. the label renderer picks one of three labels based on those, and the whole decision gets written to the sqlite database before sending the response back to the client. for appeals, the handler looks up the original database row, appends the appeal data, flips the status to `under_review`, and updates the log.

### Submission Flow

```
POST /submit
     │
     ▼
Rate Limiter ──429──► Client
     │
     ├──► Signal 1: LLM Classifier (Groq)        ─┐
     │                                             ├──► Confidence Scorer ──► Label ──► Audit Log ──► Client
     └──► Signal 2: Stylometric Analyzer (Python) ─┘
```

### Appeal Flow

```
POST /appeal/<content_id>
     │
     ▼
Rate Limiter ──429──► Client
     │
     ▼
Appeal Handler ──404──► Client
     │
     ▼
Audit Log ──► Client
```

---

## Detection Signals

**signal 1 — llm classifier (groq / llama-3.3-70b-versatile)**

sends the text to groq with a prompt asking if it sounds like a human wrote it or if it was ai-generated. returns a float `llm_score` between 0 (human) and 1 (ai).

- captures general writing style like voice, word choices, structural patterns, and that weirdly smooth phrasing ai always has.

**signal 2 — stylometric analyzer (pure python)**

computes four structural metrics on the text and averages them into a float `stylo_score` between 0 (human-like) and 1 (ai-like):

1. **sentence-length variance** — ai has lower variance because sentence lengths are super uniform and flat.
2. **type-token ratio** — vocabulary diversity; ai tends to repeat the same common words more at scale.
3. **punctuation density** — humans use expressive punctuation like commas, dashes, and question marks way more variably.
4. **average sentence length** — ai avoids super short or super long sentences and stays in a safe middle zone.

- captures statistical structure that the llm might miss.
- blind spots: texts under 3 sentences (variance stats break and look random); formal human prose (legal, academic) looks like ai because it is naturally uniform.

**combining signals:**

```
combined  = 0.65 * llm_score + 0.35 * stylo_score
agreement = 1 - |llm_score - stylo_score|
confidence = 0.5 * (2 * |combined - 0.5|) + 0.5 * agreement
```

the llm gets a higher weight (0.65) because it's a stronger detector overall. the stylometric signal gets 0.35 as a structural cross-check. agreement penalizes the confidence if the two signals disagree, which stops the system from showing high confidence when the detectors point in opposite directions.

---

## Uncertainty Representation

a confidence score of **0.6** means the system has a guess but isn't super sure — the signals probably don't agree strongly or the combined score is near the middle. this maps to the "uncertain" label instead of a firm attribution.

| Condition | Label |
|---|---|
| `confidence >= 0.55` and `combined >= 0.6` | likely_ai |
| `confidence >= 0.55` and `combined <= 0.4` | likely_human |
| anything else | uncertain |

the uncertain band is intentionally wide (combined 0.4 to 0.6) because of the asymmetry of errors: falsely accusing a human creator of using ai is way worse than missing an ai-generated post. when in doubt, the system defaults to uncertain.

---

## Transparency Labels

**high-confidence ai:**
> "This content shows strong indicators of AI generation (high confidence). This is an automated assessment — the creator may appeal if this is incorrect."

**high-confidence human:**
> "This content shows strong indicators of human authorship (high confidence). This is an automated assessment."

**uncertain:**
> "The system could not confidently determine whether this content was written by a human or AI. This may happen with short texts, edited prose, or content that blends both styles. The creator may appeal if this classification is incorrect."

---

## Appeals Workflow

- **who can appeal:** any creator with a `creator_id`, but only for their own `content_id`.
- **what they provide:** `creator_id` and some free-text `reasoning` explaining why the classification is wrong.
- **what the system does:**
  1. looks up the original audit record using `content_id` (returns 404 if not found).
  2. appends the new appeal object `{appeal_id, creator_id, reasoning, timestamp}` to the list.
  3. flips the database `status` field from `"classified"` to `"under_review"`.
  4. writes the updated record back to the sqlite database.
  5. returns the status and a message confirming it.
- **what a reviewer sees (via `GET /log`):** the full original decision (individual signal scores, combined score, confidence, label variant) along with all appeal entries showing the reasoning and timestamps.

automated re-classification doesn't happen — the appeal just flags the record so a human moderator can check it.

---

## Edge Cases

**1. short lyric poetry (less than 30 words)**
sentence variance stats are useless on 1 or 2 lines. the llm also has almost nothing to work with. both signals will output middle-ground scores near 0.5, confidence will be low, and the system will output "uncertain". this is the right behavior but might annoy creators of flash fiction or poetry.

**2. heavily edited or polished human writing**
essays revised a bunch of times lose their natural sentence length variance. the stylometric signal might flag this as ai-like. if the llm also thinks it's too polished, it might trigger a false positive. the confidence agreement check should catch this unless both signals are completely fooled.

**3. ai output prompted to "write like a casual human"**
an adversary who prompts an ai to include typos, vary sentence lengths, and use informal punctuation can easily beat both signals. this is a known limit — the system isn't adversarial-robust. the log will show low confidence and the uncertain label directs users to the appeal path anyway.

---

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/submit` | Submit text for classification |
| POST | `/appeal` | Contest a classification |
| GET | `/log` | View audit log entries |
| GET | `/health` | Liveness check |

---

## AI Tool Plan

### M3 — Submission endpoint + first signal

provide architecture diagram, signal 1 specs, and endpoints. ask for the basic flask app skeleton with `POST /submit` stub, and `signals/llm_classifier.py` calling groq's llama API. verify by calling the classifier function on some test texts.

### M4 — Second signal + confidence scoring

provide signal 2 specs and scoring formulas. ask for `signals/stylometric.py` computing the 4 stats, and `scoring.py` combining them. verify that the combined score varies between clear human and clear ai.

### M5 — Production layer

provide label text variants, appeal workflow details, and limiter specs. ask for the appeal and log routes, flask-limiter config, and sqlite db setup. verify by testing the limits and checking that appeals update the db status correctly.

---

## Implementation Phases

- [x] Phase 1 — Flask app skeleton (`app.py`, `db.py`, `.env` wiring)
- [x] Phase 2 — `signals/llm_classifier.py` and `signals/stylometric.py`
- [x] Phase 3 — `pipeline.py`, `confidence.py`, `labels.py`
- [x] Phase 4 — All routes + Flask-Limiter config
- [x] Phase 5 — SQLite audit log schema and helpers
- [x] Phase 6 — Manual testing with 4 sample texts, README finalized
