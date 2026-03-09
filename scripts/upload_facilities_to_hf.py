#!/usr/bin/env python3
"""
Upload data/facilities.csv to a Hugging Face Dataset repo.

Uses the Datasets library to create a dataset from the local CSV and push to the Hub.
See: https://huggingface.co/docs/datasets/en/create_dataset

Usage:
  pip install datasets
  # Auth: put HF_TOKEN=your_token in .env (same as the app), or run: python -m huggingface_hub.cli.login
  python scripts/upload_facilities_to_hf.py [REPO_ID]

Example:
  python scripts/upload_facilities_to_hf.py phanny/samhsa-facilities

If REPO_ID is omitted, you will be prompted. The dataset repo must already exist
on the Hub (create it at https://huggingface.co/datasets → New dataset).
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
CSV_PATH = DATA_DIR / "facilities.csv"

# Load .env so HF_TOKEN is available (same as app)
def _load_dotenv():
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main():
    _load_dotenv()
    if not CSV_PATH.exists():
        print(f"Error: {CSV_PATH} not found. Run scripts/download_findtreatment_data.py first.", file=sys.stderr)
        sys.exit(1)

    try:
        from datasets import load_dataset
    except ImportError as e:
        print(f"Error: {e}. Install with: pip install datasets huggingface_hub", file=sys.stderr)
        sys.exit(1)

    repo_id = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not repo_id:
        repo_id = input("Hugging Face dataset repo id (e.g. phanny/samhsa-facilities): ").strip()
    if not repo_id or "/" not in repo_id:
        print("Error: repo id must be like username/dataset-name", file=sys.stderr)
        sys.exit(1)

    if not os.environ.get("HF_TOKEN"):
        print("Error: Hugging Face token not set. Add HF_TOKEN to .env or run: python -m huggingface_hub.cli.login", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {CSV_PATH}...")
    # Create dataset from local CSV (per https://huggingface.co/docs/datasets/en/create_dataset)
    dataset = load_dataset("csv", data_files=str(CSV_PATH), split="train")
    print(f"Uploading to {repo_id}...")
    dataset.push_to_hub(repo_id, private=False)
    print(f"Done. Use in your Space: set variable FACILITIES_DATASET={repo_id}")
    print("Then load in code: load_dataset({!r}, split='train')".format(repo_id))


if __name__ == "__main__":
    main()
