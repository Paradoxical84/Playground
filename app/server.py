"""Flask API serving a TensorFlow model with health/readiness probes and structured logging."""

import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import tensorflow as tf
from flask import Flask, jsonify, request

# ---------------------------------------------------------------------------
# Structured JSON logging
# ---------------------------------------------------------------------------

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


def _configure_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())


_configure_logging()
log = logging.getLogger("ai-lab")

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------

app = Flask(__name__)
model: tf.keras.Model | None = None
ready = False

MODEL_DIR = os.environ.get("MODEL_DIR", "/app/model")
STARTUP_DELAY = int(os.environ.get("STARTUP_DELAY", "0"))

# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def load_model():
    global model, ready
    if STARTUP_DELAY > 0:
        log.warning("Simulating slow startup: sleeping %d seconds", STARTUP_DELAY)
        time.sleep(STARTUP_DELAY)

    model_path = Path(MODEL_DIR)
    if not model_path.exists():
        log.error("MODEL_DIR does not exist: %s", MODEL_DIR)
        raise FileNotFoundError(f"MODEL_DIR not found: {MODEL_DIR}")

    log.info("Loading model from %s", MODEL_DIR)
    model = tf.keras.models.load_model(MODEL_DIR)
    ready = True
    log.info("Model loaded successfully")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/healthz")
def healthz():
    """Liveness probe — returns 200 as long as the process is alive."""
    return jsonify({"status": "alive"}), 200


@app.route("/readyz")
def readyz():
    """Readiness probe — returns 200 only after the model is loaded."""
    if ready:
        return jsonify({"status": "ready"}), 200
    return jsonify({"status": "not_ready"}), 503


@app.route("/predict", methods=["POST"])
def predict():
    """Run inference. Expects JSON: {"instances": [[...], ...]}"""
    if not ready:
        return jsonify({"error": "Model not loaded yet"}), 503

    body = request.get_json(force=True)
    instances = body.get("instances")
    if instances is None:
        return jsonify({"error": "Missing 'instances' key"}), 400

    try:
        input_data = np.array(instances, dtype=np.float32)
        predictions = model.predict(input_data, verbose=0)
        return jsonify({"predictions": predictions.tolist()})
    except Exception as exc:
        log.exception("Prediction failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/info")
def info():
    """Return runtime metadata useful for debugging."""
    return jsonify({
        "model_dir": MODEL_DIR,
        "model_loaded": ready,
        "tensorflow_version": tf.__version__,
        "startup_delay": STARTUP_DELAY,
        "hostname": os.environ.get("HOSTNAME", "unknown"),
    })


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    port = int(os.environ.get("PORT", "8080"))
    log.info("Starting server on port %d", port)
    try:
        load_model()
    except Exception:
        log.exception("Failed to load model at startup")
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
