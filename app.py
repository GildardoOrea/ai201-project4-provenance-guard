from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import storage
from scoring import classify, combine_signals, generate_label
from signals import get_llm_signal, get_stylometric_signal

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

storage.init_db()


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    creator_id = data.get("creator_id", "anonymous")

    if not text:
        return jsonify({"error": "text field is required"}), 400

    llm_result = get_llm_signal(text)
    stylo_result = get_stylometric_signal(text)

    llm_score = llm_result["ai_probability"]
    stylo_score = stylo_result["ai_probability"]

    confidence = combine_signals(llm_score, stylo_score)
    attribution = classify(confidence)
    label = generate_label(confidence)

    content_id = storage.new_content_id()
    storage.save_submission(
        content_id, creator_id, text, attribution, confidence,
        llm_score, stylo_score, label,
    )
    storage.log_event(content_id, "submission", {
        "creator_id": creator_id,
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": llm_score,
        "stylometric_score": stylo_score,
        "llm_reasoning": llm_result.get("reasoning"),
        "stylometric_metrics": stylo_result.get("metrics"),
        "status": "classified",
    })

    return jsonify({
        "content_id": content_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
        "signals": {
            "llm_ai_probability": llm_score,
            "stylometric_ai_probability": stylo_score,
        },
    })


@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json(silent=True) or {}
    content_id = data.get("content_id")
    creator_reasoning = data.get("creator_reasoning", "").strip()

    if not content_id or not creator_reasoning:
        return jsonify({"error": "content_id and creator_reasoning are required"}), 400

    submission = storage.get_submission(content_id)
    if not submission:
        return jsonify({"error": "content_id not found"}), 404

    storage.update_submission_status(content_id, "under_review")
    storage.log_event(content_id, "appeal", {
        "creator_id": submission["creator_id"],
        "creator_reasoning": creator_reasoning,
        "original_attribution": submission["attribution"],
        "original_confidence": submission["confidence"],
        "status": "under_review",
    })

    return jsonify({
        "content_id": content_id,
        "status": "under_review",
        "message": "Appeal received and logged. A human reviewer will examine this classification.",
    })


@app.route("/log", methods=["GET"])
def log():
    limit = request.args.get("limit", default=50, type=int)
    return jsonify({"entries": storage.get_log(limit)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
