import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from db import init_db, insert_decision, get_decision, update_decision, get_log
from signals.llm_classifier import classify as llm_classify
from signals.stylometric import analyze as stylo_analyze
from scoring import score as compute_score

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

init_db()


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute; 100 per day")
def submit():
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    creator_id = body.get("creator_id", "").strip()

    if not text or not creator_id:
        return jsonify({"error": "text and creator_id are required"}), 400
    if len(text.split()) < 5:
        return jsonify({"error": "text is too short to analyze (minimum 5 words)"}), 422

    content_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    # --- Signal 1: LLM classifier ---
    llm_score = llm_classify(text)

    # --- Signal 2: Stylometric analyzer ---
    stylo_result = stylo_analyze(text)
    stylo_score = stylo_result["stylo_score"]

    # --- Confidence scoring: combine both signals ---
    scored = compute_score(llm_score, stylo_score)

    record = {
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": timestamp,
        "llm_score": llm_score,
        "stylo_score": stylo_score,
        "combined": scored["combined"],
        "confidence": scored["confidence"],
        "attribution": scored["attribution"],
        "label_variant": scored["label_variant"],
        "label": scored["label"],
        "status": "classified",
        "appeals": [],
    }

    insert_decision(record)

    return jsonify({
        "content_id": content_id,
        "attribution": record["attribution"],
        "confidence": record["confidence"],
        "label_variant": record["label_variant"],
        "label": record["label"],
        "signals": {
            "llm_score": llm_score,
            "stylo_score": stylo_score,
            "stylo_breakdown": stylo_result["breakdown"],
            "combined": scored["combined"],
        },
        "status": "classified",
    })


@app.route("/appeal/<content_id>", methods=["POST"])
@limiter.limit("5 per hour")
def appeal(content_id):
    body = request.get_json(silent=True) or {}
    creator_id = body.get("creator_id", "anonymous").strip()
    reasoning = body.get("reasoning", body.get("creator_reasoning", "")).strip()

    if not reasoning:
        return jsonify({"error": "reasoning or creator_reasoning is required"}), 400

    record = get_decision(content_id)
    if record is None:
        return jsonify({"error": "content_id not found"}), 404

    appeal_entry = {
        "appeal_id": str(uuid.uuid4()),
        "creator_id": creator_id,
        "creator_reasoning": reasoning,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    appeals = record["appeals"] + [appeal_entry]
    update_decision(content_id, {"status": "under_review", "appeals": appeals})

    return jsonify({
        "content_id": content_id,
        "appeal_id": appeal_entry["appeal_id"],
        "status": "under_review",
        "message": "Your appeal has been recorded and this content is now marked for human review.",
    })


# M5 spec route: POST /appeal with content_id in body
@app.route("/appeal", methods=["POST"])
@limiter.limit("5 per hour")
def appeal_flat():
    body = request.get_json(silent=True) or {}
    content_id = body.get("content_id", "").strip()
    creator_reasoning = body.get("creator_reasoning", body.get("reasoning", "")).strip()
    creator_id = body.get("creator_id", "anonymous").strip()

    if not content_id:
        return jsonify({"error": "content_id is required"}), 400
    if not creator_reasoning:
        return jsonify({"error": "creator_reasoning is required"}), 400

    record = get_decision(content_id)
    if record is None:
        return jsonify({"error": "content_id not found"}), 404

    appeal_entry = {
        "appeal_id": str(uuid.uuid4()),
        "creator_id": creator_id,
        "creator_reasoning": creator_reasoning,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    appeals = record["appeals"] + [appeal_entry]
    update_decision(content_id, {"status": "under_review", "appeals": appeals})

    return jsonify({
        "content_id": content_id,
        "appeal_id": appeal_entry["appeal_id"],
        "status": "under_review",
        "message": "Your appeal has been recorded and this content is now marked for human review.",
    })


@app.route("/log")
def log():
    limit = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))
    entries, total = get_log(limit, offset)
    return jsonify({"entries": entries, "total": total})


if __name__ == "__main__":
    app.run(debug=True)
