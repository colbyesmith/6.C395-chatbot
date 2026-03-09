"""
Ingest facility data from N-SUMHSS / National Directory into app schema.

Reads a CSV or Excel file (e.g. downloaded from SAMHSA N-SUMHSS or National
Directory), maps columns to the internal schema using a configurable mapping,
and writes data/facilities.csv. If the source uses codes, extend SOURCE_TO_APP
or add a code-resolution step using the N-SUMHSS codebook.

Usage:
  python scripts/ingest_facilities.py [path_to_source.csv]
  python scripts/ingest_facilities.py path/to/national_directory.xlsx

If no path is given, reads from stdin (CSV) or exits with usage.
Output: data/facilities.csv (same directory as this script: repo root/data/).
"""

import argparse
import sys
import warnings
from pathlib import Path

import pandas as pd

# Repo root (parent of scripts/)
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_CSV = DATA_DIR / "facilities.csv"

# Internal schema: only columns we need (no duplicate/redundant attribute columns).
# Search matches against "services" for treatment type, payment, languages, populations, substances.
APP_COLUMNS = [
    "facility_name",
    "address",
    "city",
    "state",
    "zip",
    "phone",
    "mat",
    "services",
]

# Map source column names (lowercase) -> app column name.
# N-SUMHSS / National Directory use different names; adjust per codebook.
# National Directory Excel may use "Facility/Program Name", "Street", "City", "State", etc.
# See data/README.md for the data story and mapping notes.
SOURCE_TO_APP = {
    "facility_name": "facility_name",
    "facility name": "facility_name",
    "facility/program name": "facility_name",
    "program name": "facility_name",
    "name": "facility_name",
    "name1": "facility_name",
    "name2": "facility_name",
    "provider name": "facility_name",
    "organization": "facility_name",
    "treatment facility name": "facility_name",
    "location name": "facility_name",
    "facility": "facility_name",
    "address": "address",
    "street": "address",
    "street address": "address",
    "address1": "address",
    "address line 1": "address",
    "street1": "address",
    "street2": "address",
    "physical address": "address",
    "location address": "address",
    "city": "city",
    "state": "state",
    "state abbreviation": "state",
    "zip": "zip",
    "zipcode": "zip",
    "zip code": "zip",
    "phone": "phone",
    "telephone": "phone",
    "phone number": "phone",
    "treatment_type": "treatment_type",
    "treatment type": "treatment_type",
    "type of care": "treatment_type",
    "care type": "treatment_type",
    "service setting": "treatment_type",
    "treatment setting": "treatment_type",
    "level of care": "treatment_type",
    "payment_options": "payment_options",
    "payment": "payment_options",
    "payment options": "payment_options",
    "payment accepted": "payment_options",
    "accepted payment": "payment_options",
    "insurance accepted": "payment_options",
    "sliding fee": "payment_options",
    "fee scale": "payment_options",
    "mat": "mat",
    "medication_assisted": "mat",
    "medication assisted": "mat",
    "medication assisted treatment": "mat",
    "buprenorphine": "mat",
    "services": "services",
    "services offered": "services",
    "service codes": "services",
    "types of care": "services",
    "substances_addressed": "substances_addressed",
    "substances": "substances_addressed",
    "substances addressed": "substances_addressed",
    "primary focus": "substances_addressed",
    "substance focus": "substances_addressed",
    "drugs treated": "substances_addressed",
    "languages": "languages",
    "language": "languages",
    "languages spoken": "languages",
    "non-english languages": "languages",
    "language services": "languages",
    "populations": "populations",
    "population": "populations",
    "population served": "populations",
    "special populations": "populations",
    "ages served": "populations",
    "age group": "populations",
    "description": "description",
    "comments": "description",
    "notes": "description",
}


def _normalize_mat(val) -> str:
    """Map various MAT values to yes/no."""
    if pd.isna(val):
        return ""
    s = str(val).lower().strip()
    if s in ("yes", "1", "true", "y"):
        return "yes"
    if s in ("no", "0", "false", "n", ""):
        return "no"
    return "yes" if "yes" in s or "offer" in s else "no"


def load_code_key(path: str | Path) -> dict[str, str] | None:
    """Load the code reference sheet from a National Directory Excel and return code -> description dict.
    SAMHSA 2024 uses sheet 'Service Code Reference' with service_code and service_name columns.
    """
    path = Path(path)
    if path.suffix.lower() not in (".xlsx", ".xls"):
        return None
    if not path.exists():
        return None
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*Cannot parse header or footer.*")
        xl = pd.ExcelFile(path)
    key_df = None
    for name in xl.sheet_names:
        nlower = name.lower()
        if "service code reference" in nlower or "code reference" in nlower or ("key" in nlower and "code" in nlower):
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*Cannot parse header or footer.*")
                key_df = pd.read_excel(path, sheet_name=name)
            break
    if key_df is None:
        for name in xl.sheet_names:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*Cannot parse header or footer.*")
                sheet = pd.read_excel(path, sheet_name=name)
            if 2 <= len(sheet) <= 600 and len(sheet.columns) >= 2:
                cols_lower = [str(c).lower() for c in sheet.columns]
                if "service_code" in cols_lower and "service_name" in cols_lower:
                    key_df = sheet
                    break
    if key_df is None or len(key_df) == 0:
        return None
    key_df.columns = [str(c).strip() for c in key_df.columns]
    cols_lower = [c.lower() for c in key_df.columns]
    code_col = None
    desc_col = None
    if "service_code" in cols_lower:
        code_col = key_df.columns[cols_lower.index("service_code")]
    if "service_name" in cols_lower:
        desc_col = key_df.columns[cols_lower.index("service_name")]
    if not code_col or not desc_col:
        code_col = key_df.columns[0]
        desc_col = key_df.columns[1] if len(key_df.columns) > 1 else key_df.columns[0]
    code_key = {}
    for _, row in key_df.iterrows():
        k = str(row.get(code_col, "")).strip()
        v = str(row.get(desc_col, "")).strip()
        if k and v and k != "nan" and v != "nan" and len(k) <= 20:
            code_key[k] = v
    return code_key if code_key else None


def _decode_service_codes(series: pd.Series, code_key: dict[str, str]) -> pd.Series:
    """Replace code tokens with descriptions; join with ', '. Skip * and unknown tokens (only output decoded)."""
    def decode_one(cell: str) -> str:
        if pd.isna(cell) or not str(cell).strip():
            return ""
        parts = []
        for token in str(cell).split():
            token = token.strip()
            if not token or token == "*":
                continue
            if token in code_key:
                parts.append(code_key[token])
        return ", ".join(parts) if parts else ""
    return series.apply(decode_one)


def load_source(path: str | Path) -> pd.DataFrame:
    """Load CSV or Excel into a DataFrame with lowercase column names.
    For Excel with multiple sheets (e.g. National Directory + Key), uses the
    sheet that looks like facility data (has facility name or state, and many rows).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    suf = path.suffix.lower()
    if suf == ".csv":
        df = pd.read_csv(path)
    elif suf in (".xlsx", ".xls"):
        # Suppress openpyxl header/footer parse warnings (harmless; SAMHSA Excel often has them)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*Cannot parse header or footer.*")
            xl = pd.ExcelFile(path)
        if len(xl.sheet_names) == 1:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*Cannot parse header or footer.*")
                df = pd.read_excel(path)
        else:
            # Pick the sheet that has facility data: prefer one with a facility-name-like column and many rows
            def sheet_has_facility_name_col(sheet: pd.DataFrame) -> bool:
                cols_lower = [str(c).lower().strip() for c in sheet.columns]
                if "facility name" in cols_lower or "facility_name" in cols_lower:
                    return True
                if "program name" in cols_lower or "facility/program name" in cols_lower:
                    return True
                if any(("facility" in c or "program" in c) and "name" in c for c in cols_lower):
                    return True
                if "organization" in cols_lower or "provider name" in cols_lower:
                    return True
                return False

            best = None
            best_score = -1
            for name in xl.sheet_names:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message=".*Cannot parse header or footer.*")
                    sheet = pd.read_excel(path, sheet_name=name)
                if len(sheet) < 10:
                    continue
                cols_lower = [str(c).lower().strip() for c in sheet.columns]
                has_state_city = "state" in cols_lower and "city" in cols_lower
                has_name_col = sheet_has_facility_name_col(sheet)
                # Strongly prefer sheet that has a facility name column; then state/city; then row count
                score = (1000 if has_name_col else 0) + (10 if has_state_city else 0) + min(len(sheet), 5000)
                if score > best_score:
                    best_score = score
                    best = sheet
            if best is not None:
                df = best
            else:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message=".*Cannot parse header or footer.*")
                    df = pd.read_excel(path, sheet_name=0)
    else:
        raise ValueError(f"Unsupported format: {suf}. Use .csv or .xlsx")
    df.columns = [str(c).lower().strip() for c in df.columns]
    return df


def _guess_facility_name_column(df: pd.DataFrame, col_map: dict) -> str | None:
    """If no facility_name mapping, find a column that likely holds facility/program name."""
    if "facility_name" in col_map:
        return None
    for src_col in df.columns:
        c = str(src_col).lower().strip()
        if "program" in c and "name" in c:
            return src_col
        if "facility" in c and "name" in c:
            return src_col
        if c in ("organization", "provider name", "location name"):
            return src_col
        # First column is often the name in directory layouts
        if list(df.columns)[0] == src_col and ("name" in c or "facility" in c or "program" in c):
            return src_col
    return None


def _guess_address_column(df: pd.DataFrame, col_map: dict) -> str | None:
    """If no address mapping, find a column that likely holds street address."""
    if "address" in col_map:
        return None
    for src_col in df.columns:
        c = str(src_col).lower().strip()
        if "street" in c or ("address" in c and "line" in c):
            return src_col
        if c in ("physical address", "location address"):
            return src_col
    return None


# Keywords to try when guessing unmapped columns (app_col -> list of substrings; any match in column name).
_GUESS_COLUMN_KEYWORDS = {
    "treatment_type": ["treatment type", "type of care", "care type", "service setting", "level of care", "setting"],
    "payment_options": ["payment", "insurance", "fee", "sliding", "medicaid", "accepted payment"],
    "services": ["services", "service codes", "types of care", "offered", "treatment modalities"],
    "substances_addressed": ["substance", "primary focus", "drug", "alcohol", "opioid"],
    "languages": ["language", "non-english", "spanish", "bilingual"],
    "populations": ["population", "age", "special population", "veteran", "gender", "served"],
    "description": ["description", "comments", "notes", "remarks"],
}


def _guess_column_by_keywords(df: pd.DataFrame, col_map: dict, app_col: str) -> str | None:
    """If app_col not yet mapped, find a source column whose name contains any of the keywords."""
    if app_col in col_map:
        return None
    keywords = _GUESS_COLUMN_KEYWORDS.get(app_col, [])
    for src_col in df.columns:
        c = str(src_col).lower().strip()
        for kw in keywords:
            if kw in c:
                return src_col
    return None


def map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map source columns to app schema; add missing app columns as empty."""
    out = {}
    for app_col in APP_COLUMNS:
        out[app_col] = []
    # Find which source column maps to each app column
    col_map = {}
    for src_col in df.columns:
        src_lower = str(src_col).lower().strip()
        if src_lower in SOURCE_TO_APP:
            app_col = SOURCE_TO_APP[src_lower]
            if app_col not in col_map:
                col_map[app_col] = src_col
    # Fallbacks for National Directory Excel when headers differ
    guess_name = _guess_facility_name_column(df, col_map)
    if guess_name and "facility_name" not in col_map:
        col_map["facility_name"] = guess_name
    guess_addr = _guess_address_column(df, col_map)
    if guess_addr and "address" not in col_map:
        col_map["address"] = guess_addr
    for app_col in ("treatment_type", "payment_options", "services", "substances_addressed", "languages", "populations", "description"):
        guess = _guess_column_by_keywords(df, col_map, app_col)
        if guess and app_col not in col_map:
            col_map[app_col] = guess
    for app_col in APP_COLUMNS:
        if app_col in col_map:
            out[app_col] = df[col_map[app_col]].astype(str).replace("nan", "").tolist()
        else:
            out[app_col] = [""] * len(df)
    result = pd.DataFrame(out)

    # National Directory format: merge name1+name2 -> facility_name, street1+street2 -> address
    cols_lower = [str(c).lower().strip() for c in df.columns]
    if "name1" in cols_lower and "name2" in cols_lower:
        n1 = df["name1"].astype(str).replace("nan", "").str.strip()
        n2 = df["name2"].astype(str).replace("nan", "").str.strip()
        merged = (n1 + " " + n2).str.strip()
        result["facility_name"] = merged.where(merged != "", result["facility_name"])
    if "street1" in cols_lower and "street2" in cols_lower:
        s1 = df["street1"].astype(str).replace("nan", "").str.strip()
        s2 = df["street2"].astype(str).replace("nan", "").str.strip()
        merged = (s1 + " " + s2).str.strip()
        result["address"] = merged.where(merged != "", result["address"])
    # service_code_info is decoded in main() using the Key sheet when available (see load_code_key).

    # Normalize MAT to yes/no
    if "mat" in result.columns:
        result["mat"] = result["mat"].apply(_normalize_mat)
    return result


def drop_missing_location(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only rows with non-empty city and state."""
    if "city" not in df.columns or "state" not in df.columns:
        return df
    return df[
        df["city"].notna() & (df["city"].astype(str).str.strip() != "")
        & df["state"].notna() & (df["state"].astype(str).str.strip() != "")
    ].copy()


def main():
    ap = argparse.ArgumentParser(description="Ingest N-SUMHSS/National Directory data into facilities.csv")
    ap.add_argument("source", nargs="?", help="Path to source CSV or Excel file. If omitted, print usage and exit.")
    ap.add_argument("-o", "--output", default=str(OUTPUT_CSV), help="Output CSV path")
    args = ap.parse_args()
    if not args.source:
        ap.print_help()
        sys.exit(0)
    path = Path(args.source)
    raw_df = load_source(path)
    df = map_columns(raw_df)
    if df["facility_name"].str.strip().eq("").all():
        print(
            "Warning: no facility names were mapped. Source columns were:\n  "
            + ", ".join(repr(c) for c in raw_df.columns),
            file=sys.stderr,
        )
    # Decode service_code_info using the Key sheet; store only in services (search uses it for all filters).
    if "service_code_info" in raw_df.columns and path.suffix.lower() in (".xlsx", ".xls"):
        code_key = load_code_key(path)
        if code_key:
            decoded = _decode_service_codes(raw_df["service_code_info"], code_key)
            df["services"] = decoded
    # Report if services is still empty (couldn't decode)
    empty_attrs = [c for c in ("services",) if c in df.columns and (df[c].astype(str).str.strip() == "").all()]
    if empty_attrs and "service_code_info" in raw_df.columns:
        print(
            "Note: " + ", ".join(empty_attrs) + " had no data (source has coded service_code_info; "
            "Key sheet not found or could not be parsed for decoding).",
            file=sys.stderr,
        )
    elif empty_attrs:
        print(
            "Note: these attributes had no data after mapping: " + ", ".join(empty_attrs) + ".",
            file=sys.stderr,
        )
    df = drop_missing_location(df)
    # Deduplicate by facility_name + address + city + state (keep first occurrence)
    key_cols = ["facility_name", "address", "city", "state"]
    if all(c in df.columns for c in key_cols):
        before = len(df)
        df = df.drop_duplicates(subset=key_cols, keep="first").reset_index(drop=True)
        if len(df) < before:
            print(f"Dropped {before - len(df)} duplicate rows (same name+address+city+state).", file=sys.stderr)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"Wrote {len(df)} rows to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
