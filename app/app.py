"""Flask inference API with health/readiness probes and per-request logging."""

import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import tensorflow as tf
from flask import Flask, jsonify, request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL_DIR = os.environ.get("MODEL_DIR", "/model")
STARTUP_DELAY_SEC = int(os.environ.get("STARTUP_DELAY_SEC", "0"))
PORT = int(os.environ.get("PORT", "8080"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger("ai-lab")

# ---------------------------------------------------------------------------
# App + state
# ---------------------------------------------------------------------------

app = Flask(__name__)
_model = None
_ready = False
_load_error = None

# ---------------------------------------------------------------------------
# Request logging (method, path, status, latency_ms)
# ---------------------------------------------------------------------------

@app.before_request
def _start_timer():
    request._start_time = time.perf_counter()


@app.after_request
def _log_request(response):
    latency_ms = (time.perf_counter() - request._start_time) * 1000.0
    log.info(
        "%s %s %s %.1fms",
        request.method,
        request.path,
        response.status_code,
        latency_ms,
    )
    return response

# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def _load_model():
    global _model, _ready, _load_error

    if STARTUP_DELAY_SEC > 0:
        log.warning("Simulating slow startup: sleeping %d s …", STARTUP_DELAY_SEC)
        time.sleep(STARTUP_DELAY_SEC)

    model_path = Path(MODEL_DIR)
    if not model_path.exists():
        _load_error = f"MODEL_DIR path does not exist: {MODEL_DIR}"
        log.error(_load_error)
        raise FileNotFoundError(_load_error)

    log.info("Loading SavedModel from %s …", MODEL_DIR)
    try:
        _model = tf.keras.models.load_model(MODEL_DIR)
    except Exception as exc:
        _load_error = f"Failed to load model from {MODEL_DIR}: {exc}"
        log.error(_load_error)
        raise

    _ready = True
    log.info("Model loaded – server is ready")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/healthz")
def healthz():
    """Liveness — 200 whenever the process is alive."""
    return jsonify({"status": "alive"}), 200


@app.route("/readyz")
def readyz():
    """Readiness — 200 only after the model is loaded."""
    if _ready:
        return jsonify({"status": "ready"}), 200
    body = {"status": "not_ready"}
    if _load_error:
        body["error"] = _load_error
    return jsonify(body), 503


@app.route("/predict", methods=["POST"])
def predict():
    """Regression inference.  Expects {"x": <number>}, returns {"x": …, "y": …}."""
    if not _ready:
        return jsonify({"error": "model not loaded"}), 503

    body = request.get_json(force=True)
    x_val = body.get("x")
    if x_val is None:
        return jsonify({"error": "missing key 'x'"}), 400

    try:
        x_arr = np.array([[float(x_val)]], dtype=np.float32)
        y_arr = _model.predict(x_arr, verbose=0)
        return jsonify({"x": float(x_val), "y": float(y_arr[0][0])})
    except Exception as exc:
        log.exception("Prediction failed")
        return jsonify({"error": str(exc)}), 500

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    log.info("PORT=%d  MODEL_DIR=%s  STARTUP_DELAY_SEC=%d", PORT, MODEL_DIR, STARTUP_DELAY_SEC)
    try:
        _load_model()
    except Exception:
        log.exception("Model load failed at startup — readyz will return 503")
    app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
