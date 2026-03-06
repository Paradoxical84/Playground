import json
import shutil
from pathlib import Path

import numpy as np
import tensorflow as tf


MODEL_OUTPUT_DIR = Path("models/demo-model")


def build_dataset(sample_count: int = 2048) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(42)
    features = rng.uniform(low=-2.0, high=2.0, size=(sample_count, 2)).astype(np.float32)
    labels = (3.0 * features[:, 0] - 2.0 * features[:, 1] + 1.0).astype(np.float32)
    return features, labels


def build_model() -> tf.keras.Model:
    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(2,)),
            tf.keras.layers.Dense(8, activation="relu"),
            tf.keras.layers.Dense(1),
        ]
    )
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.05), loss="mse")
    return model


def main() -> None:
    tf.keras.utils.set_random_seed(42)

    x_train, y_train = build_dataset()
    model = build_model()
    history = model.fit(x_train, y_train, epochs=30, batch_size=64, verbose=0)

    predictions = model.predict(x_train[:128], verbose=0).reshape(-1)
    mse = float(np.mean(np.square(predictions - y_train[:128])))

    MODEL_OUTPUT_DIR.parent.mkdir(parents=True, exist_ok=True)
    if MODEL_OUTPUT_DIR.exists():
        shutil.rmtree(MODEL_OUTPUT_DIR)

    model.save(str(MODEL_OUTPUT_DIR))

    metadata = {
        "model_dir": str(MODEL_OUTPUT_DIR),
        "final_loss": float(history.history["loss"][-1]),
        "sample_mse": mse,
    }
    metadata_path = MODEL_OUTPUT_DIR.parent / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
