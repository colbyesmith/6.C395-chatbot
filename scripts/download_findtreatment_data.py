"""
Download the full facility dataset that powers FindTreatment.gov.

SAMHSA publishes the National Directory of Drug and Alcohol Use Treatment
Facilities (same data source as FindTreatment.gov). This script downloads the
official Excel file and runs the ingest to produce data/facilities.csv so the
chatbot uses all treatment centers, not just the sample in the repo.

Usage:
  python scripts/download_findtreatment_data.py

Downloads to data/National_Directory_SU_2024.xlsx (or current year), then
runs the ingest to write data/facilities.csv. Requires: requests, pandas, openpyxl.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# Official SAMHSA 2024 National Directory (substance use treatment facilities).
# Same data that powers https://findtreatment.gov
NATIONAL_DIRECTORY_URL = (
    "https://www.samhsa.gov/data/sites/default/files/reports/rpt53015/"
    "National%20Directory%20SU%202024_Final.xlsx"
)
DOWNLOAD_FILENAME = "National_Directory_SU_2024.xlsx"


def download_file(url: str, dest: Path) -> None:
    """Download url to dest using urllib (no extra deps)."""
    try:
        from urllib.request import urlretrieve
        urlretrieve(url, dest)
    except Exception as e:
        # Fallback: try requests if available
        try:
            import requests
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            dest.write_bytes(r.content)
        except ImportError:
            raise RuntimeError(
                f"Download failed: {e}. Install requests (pip install requests) and try again."
            ) from e


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / DOWNLOAD_FILENAME
    print(f"Downloading FindTreatment.gov dataset from SAMHSA...", file=sys.stderr)
    print(f"  URL: {NATIONAL_DIRECTORY_URL}", file=sys.stderr)
    try:
        download_file(NATIONAL_DIRECTORY_URL, dest)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Saved to {dest}", file=sys.stderr)
    # Run ingest to produce facilities.csv
    print("Running ingest to build data/facilities.csv...", file=sys.stderr)
    import subprocess
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "ingest_facilities.py"), str(dest), "-o", str(DATA_DIR / "facilities.csv")],
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        print(
            "\nIngest failed (often due to missing openpyxl). Install dependencies:\n"
            "  pip install -r requirements.txt\n"
            "Then run ingest manually:\n"
            f"  python scripts/ingest_facilities.py {dest} -o data/facilities.csv",
            file=sys.stderr,
        )
        sys.exit(result.returncode)
    print("Done. The chatbot now uses the full FindTreatment.gov dataset.", file=sys.stderr)


if __name__ == "__main__":
    main()
