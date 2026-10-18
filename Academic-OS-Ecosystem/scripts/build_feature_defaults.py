"""
Write model_artifacts/feature_defaults.json.

The placement model needs 15 raw inputs. When a student has no value for an
input (not in Lumen, not self-reported), the backend substitutes the median
from the training data. These medians are written here so that the serving
path uses exactly the distribution the model was trained on.

Usage:
    python scripts/build_feature_defaults.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.features import RAW_FEATURE_COLUMNS  # noqa: E402

DATA_PATH = ROOT / "data" / "synthetic_students.csv"
OUT_PATH = ROOT / "model_artifacts" / "feature_defaults.json"


def main() -> None:
    df = pd.read_csv(DATA_PATH)
    defaults = {col: float(df[col].median()) for col in RAW_FEATURE_COLUMNS}
    payload = {
        "source": DATA_PATH.name,
        "statistic": "median",
        "rows": int(len(df)),
        "defaults": defaults,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT_PATH.relative_to(ROOT)} ({len(defaults)} features, {len(df)} rows)")


if __name__ == "__main__":
    main()
