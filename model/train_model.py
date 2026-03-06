"""Train a tiny regression model (y ≈ 2x + 1) and export as a TF SavedModel."""

import logging
import sys
from pathlib import Path

import numpy as np
import tensorflow as tf

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger("train")

SAVE_DIR = Path(__file__).resolve().parent / "saved_model"
SAMPLES = 1000
EPOCHS = 10

def main():
    np.random.seed(42)
    x = np.random.uniform(-10, 10, size=(SAMPLES, 1)).astype(np.float32)
    y = (2.0 * x + 1.0 + np.random.normal(0, 0.3, size=x.shape)).astype(np.float32)

    log.info("Training data: x %s  y %s", x.shape, y.shape)

    model = tf.keras.Sequential([
        tf.keras.layers.Dense(16, activation="relu", input_shape=(1,)),
        tf.keras.layers.Dense(8, activation="relu"),
        tf.keras.layers.Dense(1),
    ])
    model.compile(optimizer="adam", loss="mse", metrics=["mae"])
    model.summary(print_fn=log.info)

    model.fit(x, y, epochs=EPOCHS, batch_size=32, validation_split=0.2, verbose=2)

    log.info("Saving model to %s", SAVE_DIR)
    model.save(str(SAVE_DIR))
    log.info("Done – model exported to %s", SAVE_DIR)


if __name__ == "__main__":
    main()
