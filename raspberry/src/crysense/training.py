from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

from .audio_features import FEATURE_NAMES, features_from_wav
from .models import write_model_metadata

TASKS = {
    "trigger": {"classes": ("cry", "noise"), "seconds": 1.0, "filename": "trigger.joblib"},
    "type": {"classes": ("colic", "hunger"), "seconds": 6.0, "filename": "type.joblib"},
}


def collect(dataset_dir: Path, classes: tuple[str, ...], seconds: float) -> tuple[np.ndarray, np.ndarray, list[str]]:
    vectors: list[np.ndarray] = []
    labels: list[str] = []
    files: list[str] = []
    for label in classes:
        directory = dataset_dir / label
        if not directory.is_dir():
            raise RuntimeError(f"Pasta de classe ausente: {directory}")
        for path in sorted(directory.glob("*.wav")):
            try:
                vectors.append(features_from_wav(path, seconds).vector)
                labels.append(label)
                files.append(path.name)
            except Exception as exc:
                print(f"[ignorado] {path.name}: {exc}")
    if not vectors:
        raise RuntimeError("Nenhum WAV válido encontrado")
    counts = Counter(labels)
    missing = [label for label in classes if counts[label] < 2]
    if missing:
        raise RuntimeError(f"Dados insuficientes nas classes: {', '.join(missing)}")
    return np.vstack(vectors).astype(np.float32), np.asarray(labels), files


def train(task: str, dataset_dir: Path, output_dir: Path, test_size: float, trees: int) -> dict:
    config = TASKS[task]
    classes = config["classes"]
    x, y, files = collect(dataset_dir, classes, config["seconds"])
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=test_size, random_state=42, stratify=y
    )
    classifier = RandomForestClassifier(
        n_estimators=trees,
        max_depth=16,
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )
    classifier.fit(x_train, y_train)
    predictions = classifier.predict(x_test)
    report = classification_report(y_test, predictions, labels=list(classes), output_dict=True, zero_division=0)
    matrix = confusion_matrix(y_test, predictions, labels=list(classes)).tolist()

    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / config["filename"]
    joblib.dump(classifier, model_path)
    metadata = {
        "task": task,
        "created_at": datetime.now(UTC).isoformat(),
        "dataset": str(dataset_dir),
        "classes": list(classes),
        "sample_rate": 16000,
        "window_seconds": config["seconds"],
        "feature_names": list(FEATURE_NAMES),
        "feature_count": len(FEATURE_NAMES),
        "samples": len(y),
        "class_counts": dict(Counter(y)),
        "split": "estratificado aleatório por arquivo; não representa validação por fonte de gravação",
        "test_size": test_size,
        "trees": trees,
        "report": report,
        "confusion_matrix": matrix,
        "source_files": files,
    }
    write_model_metadata(model_path, metadata)
    return {"model": str(model_path), **metadata}


def main() -> None:
    parser = argparse.ArgumentParser(description="Treina os classificadores locais do CrySense")
    parser.add_argument("task", choices=TASKS)
    parser.add_argument("--dataset", type=Path, required=True, help="Pasta com as classes do dataset")
    parser.add_argument("--output", type=Path, default=Path("models"))
    parser.add_argument("--test-size", type=float, default=0.20)
    parser.add_argument("--trees", type=int, default=300)
    args = parser.parse_args()
    result = train(args.task, args.dataset, args.output, args.test_size, args.trees)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print("\nATENÇÃO: esta métrica é apenas baseline. Antes de produção, valide por gravação-origem/bebê.")


if __name__ == "__main__":
    main()
