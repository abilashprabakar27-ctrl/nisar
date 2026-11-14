"""Score a result against a labelled check-point file.

    python scripts/score.py --key <result id> --points data/drivers/patna-bihar/checkpoints.csv
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import accuracy  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--key", required=True)
ap.add_argument("--points", required=True)
a = ap.parse_args()
print(json.dumps(accuracy.score(a.key, Path(a.points)), indent=2))
