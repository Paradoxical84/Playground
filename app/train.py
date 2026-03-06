"""Train a tiny dense model on synthetic data and save it as a SavedModel."""

import argparse
import logging
import sys

import numpy as np
import tensorflow as tf


def main():
    parser = argparse.ArgumentParser(description="Train a demo model")
    parser.add_argument("--output-dir", default="model", help="Directory to save the trained model")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--samples", type=int, default=1000)
    args = parser.parse_args()

    logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("train")

    log.info("Generating %d synthetic samples", args.samples)
    np.random.seed(42)
    X = np.random.rand(args.samples, 4).astype(np.float32)
    y = (X.sum(axis=1) > 2.0).astype(np.float32)

    log.info("Building model")
    model = tf.keras.Sequential([
        tf.keras.layers.Dense(16, activation="relu", input_shape=(4,)),
        tf.keras.layers.Dense(8, activation="relu"),
        tf.keras.layers.Dense(1, activation="sigmoid"),
    ])
    model.compile(optimizer="adam", loss="binary_crossentropy", metrics=["accuracy"])

    log.info("Training for %d epochs", args.epochs)
    model.fit(X, y, epochs=args.epochs, batch_size=32, validation_split=0.2, verbose=2)

    log.info("Saving model to %s", args.output_dir)
    model.save(args.output_dir)
    log.info("Done")


if __name__ == "__main__":
    main()
