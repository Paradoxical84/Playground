import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
import tensorflow as tf

from app.logging_utils import log_event


class ModelService:
    def __init__(
        self,
        *,
        model_dir: str,
        logger: logging.Logger,
        startup_delay_seconds: int = 0,
        memory_hog_mib: int = 0,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.logger = logger
        self.startup_delay_seconds = startup_delay_seconds
        self.memory_hog_mib = memory_hog_mib
        self.memory_hog: bytearray | None = None
        self.model: tf.keras.Model | None = None
        self.load_error: str | None = None
        self.ready = False

    def initialize(self) -> None:
        if self.startup_delay_seconds > 0:
            log_event(
                self.logger,
                logging.INFO,
                "Delaying startup for probe-failure scenario",
                startup_delay_seconds=self.startup_delay_seconds,
            )
            time.sleep(self.startup_delay_seconds)

        if self.memory_hog_mib > 0:
            bytes_to_allocate = self.memory_hog_mib * 1024 * 1024
            log_event(
                self.logger,
                logging.INFO,
                "Allocating memory for OOM scenario",
                memory_hog_mib=self.memory_hog_mib,
            )
            self.memory_hog = bytearray(bytes_to_allocate)

        try:
            self.model = tf.keras.models.load_model(str(self.model_dir))
            self.ready = True
            self.load_error = None
            log_event(
                self.logger,
                logging.INFO,
                "Model loaded successfully",
                model_dir=str(self.model_dir),
            )
        except Exception as exc:
            self.ready = False
            self.load_error = str(exc)
            log_event(
                self.logger,
                logging.ERROR,
                "Model failed to load",
                model_dir=str(self.model_dir),
                error=self.load_error,
            )

    def readiness_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ready": self.ready,
            "model_dir": str(self.model_dir),
        }
        if self.load_error:
            payload["error"] = self.load_error
        return payload

    def predict(self, features: list[Any]) -> float:
        if not self.ready or self.model is None:
            raise RuntimeError(self.load_error or "Model is not ready")

        if len(features) != 2:
            raise ValueError("Exactly two numeric features are required")

        try:
            feature_values = np.asarray([features], dtype=np.float32)
        except (TypeError, ValueError) as exc:
            raise ValueError("Features must be numeric") from exc

        prediction = self.model.predict(feature_values, verbose=0)
        return float(np.asarray(prediction).squeeze())
