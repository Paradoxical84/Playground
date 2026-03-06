import logging
import os
import time
from typing import Any

from flask import Flask, Response, g, jsonify, request
from werkzeug.exceptions import HTTPException

from app.logging_utils import build_logger, log_event
from app.model_service import ModelService


def env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        return int(raw_value)
    except ValueError:
        return default


def create_app() -> Flask:
    logger = build_logger("cloud-ai-lab", os.getenv("LOG_LEVEL", "INFO"))
    model_service = ModelService(
        model_dir=os.getenv("MODEL_DIR", "/app/models/demo-model"),
        logger=logger,
        startup_delay_seconds=env_int("STARTUP_DELAY_SECONDS", 0),
        memory_hog_mib=env_int("MEMORY_HOG_MIB", 0),
    )
    model_service.initialize()

    app = Flask(__name__)
    app.config["MODEL_SERVICE"] = model_service
    app.config["LOGGER"] = logger

    @app.before_request
    def before_request() -> None:
        g.request_started_at = time.perf_counter()

    @app.after_request
    def after_request(response: Response) -> Response:
        started_at = getattr(g, "request_started_at", time.perf_counter())
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        log_event(
            app.config["LOGGER"],
            logging.INFO,
            "Request handled",
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            remote_addr=request.remote_addr,
        )
        return response

    @app.errorhandler(Exception)
    def handle_exception(exc: Exception):
        if isinstance(exc, (ValueError, RuntimeError)):
            status_code = 400 if isinstance(exc, ValueError) else 503
            log_event(
                app.config["LOGGER"],
                logging.WARNING,
                "Handled application exception",
                error=str(exc),
                status_code=status_code,
            )
            return jsonify({"error": str(exc)}), status_code

        if isinstance(exc, HTTPException):
            log_event(
                app.config["LOGGER"],
                logging.WARNING,
                "Handled HTTP exception",
                error=exc.description,
                status_code=exc.code,
            )
            return jsonify({"error": exc.description}), exc.code

        log_event(
            app.config["LOGGER"],
            logging.ERROR,
            "Unhandled exception",
            error=str(exc),
        )
        return jsonify({"error": "Internal server error"}), 500

    @app.get("/")
    def index():
        service: ModelService = app.config["MODEL_SERVICE"]
        payload = {
            "service": "cloud-ai-troubleshooting-lab",
            "ready": service.ready,
            "model_dir": str(service.model_dir),
        }
        return jsonify(payload)

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"}), 200

    @app.get("/readyz")
    def readyz():
        service: ModelService = app.config["MODEL_SERVICE"]
        payload = service.readiness_payload()
        status_code = 200 if payload["ready"] else 503
        return jsonify(payload), status_code

    @app.post("/predict")
    def predict():
        body: dict[str, Any] = request.get_json(force=True, silent=False) or {}
        features = body.get("features")
        if not isinstance(features, list):
            raise ValueError("Request body must include a JSON array at 'features'")

        service: ModelService = app.config["MODEL_SERVICE"]
        prediction = service.predict(features)
        return jsonify({"prediction": prediction}), 200

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=env_int("PORT", 8080))
