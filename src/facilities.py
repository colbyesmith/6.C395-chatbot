"""
SAMHSA facility data loading and search.

Data story: See data/README.md (source: N-SUMHSS / National Directory; scope and limitations).

Loading: Prefer local data/facilities.csv. On Hugging Face Spaces (or when FACILITIES_DATASET
is set), load the full CSV from that Dataset repo so the large file is not stored in the Space repo.
"""

import os
import pandas as pd
from typing import Any

# Set to "username/dataset-name" to load facilities from a Hugging Face Dataset (e.g. for Spaces).
FACILITIES_DATASET_ENV = "FACILITIES_DATASET"

# Column mapping: internal names -> CSV columns
FACILITY_COLUMNS = {
    "name": "facility_name",
    "address": "address",
    "city": "city",
    "state": "state",
    "zip": "zip",
    "phone": "phone",
    "treatment_type": "treatment_type",
    "payment_options": "payment_options",
    "mat": "mat",
    "services": "services",
    "substances_addressed": "substances_addressed",
    "languages": "languages",
    "populations": "populations",
    "description": "description",
}


def _data_path() -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "data", "facilities.csv")


def _load_facilities_from_dataset(repo_id: str) -> pd.DataFrame:
    """Load facilities from a Hugging Face Dataset (CSV). Returns DataFrame with same schema as local CSV."""
    try:
        from datasets import load_dataset
    except ImportError:
        return pd.DataFrame()
    try:
        full = load_dataset(repo_id, trust_remote_code=False)
        # Single CSV may be under "train" or the only split (e.g. "train" or default)
        splits = list(full.keys())
        split = "train" if "train" in splits else (splits[0] if splits else None)
        if split is None:
            return pd.DataFrame()
        df = full[split].to_pandas()
    except Exception:
        return pd.DataFrame()
    return _filter_facilities_df(df)


def _filter_facilities_df(df: pd.DataFrame) -> pd.DataFrame:
    """Keep rows with non-missing city and state."""
    if df.empty:
        return df
    for col in ["city", "state"]:
        if col in df.columns:
            df = df[df[col].notna() & (df[col].astype(str).str.strip() != "")]
    return df


def load_facilities() -> pd.DataFrame:
    """Load facility data: from HF Dataset if FACILITIES_DATASET is set, else from local data/facilities.csv."""
    repo_id = os.environ.get(FACILITIES_DATASET_ENV, "").strip()
    if repo_id:
        df = _load_facilities_from_dataset(repo_id)
        if not df.empty:
            return df
    path = _data_path()
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    return _filter_facilities_df(df)


def search(criteria: dict[str, Any], df: pd.DataFrame | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """
    Search facilities by criteria. Only returns facilities that match all provided filters.
    Criteria keys (all optional): location (state or city name), state, city, treatment_type,
    payment (e.g. Medicaid, MassHealth, insurance, sliding scale, free, veterans), mat (bool),
    populations (e.g. veterans, adolescents, LGBTQ+, pregnant women), languages (e.g. Spanish),
    substances (e.g. alcohol, opioids), therapies (e.g. CBT, 12-step; MAT is separate via mat=True).
    Missing columns (e.g. substances_addressed) are skipped for that filter.
    """
    if df is None:
        df = load_facilities()
    if df.empty:
        return []

    out = df.copy()

    # Normalize for matching: lowercase string
    def norm(s: Any) -> str:
        if pd.isna(s):
            return ""
        return str(s).lower().strip()

    # State: exact match (e.g. "ma", "MA" -> Massachusetts or state abbrev)
    state = criteria.get("state") or (criteria.get("location") if isinstance(criteria.get("location"), str) and len(criteria.get("location", "").strip()) == 2 else None)
    if not state and isinstance(criteria.get("location"), str):
        loc = criteria["location"].strip()
        # US state abbreviations (common)
        abbr = {"ma": "ma", "mass": "ma", "massachusetts": "ma", "tx": "tx", "texas": "tx", "ca": "ca", "california": "ca", "il": "il", "illinois": "il"}
        for k, v in abbr.items():
            if loc.lower().startswith(k) or k in loc.lower():
                state = v
                break
        if not state and "boston" in loc.lower():
            state = "ma"
        if not state and "austin" in loc.lower():
            state = "tx"
        if not state and "san antonio" in loc.lower():
            state = "tx"
        if not state and "chicago" in loc.lower():
            state = "il"
        if not state and ("california" in loc.lower() or "san francisco" in loc.lower() or "los angeles" in loc.lower()):
            state = "ca"
    if state:
        out = out[out["state"].astype(str).str.lower().str.strip() == norm(state)]

    # City or location text in city/name
    city = criteria.get("city")
    location_text = criteria.get("location") if not state else None
    if city:
        out = out[out["city"].apply(norm).str.contains(norm(city), na=False)]
    elif location_text and isinstance(location_text, str) and len(location_text) > 2:
        loc = norm(location_text)
        if loc not in ("ma", "tx", "ca", "il", "mass", "massachusetts", "texas", "california", "illinois"):
            out = out[
                out["city"].apply(norm).str.contains(loc, na=False)
                | out["facility_name"].apply(norm).str.contains(loc, na=False)
            ]

    # Helper: match term in col, or in services/description when col is empty (decoded data stored there)
    def col_or_services_contains(col: str, term: str) -> pd.Series:
        col_vals = out[col].apply(norm) if col in out.columns else pd.Series([""] * len(out), index=out.index)
        if "services" in out.columns:
            fallback = out["services"].apply(norm).str.contains(term, na=False)
            if "description" in out.columns:
                fallback = fallback | out["description"].apply(norm).str.contains(term, na=False)
        else:
            fallback = pd.Series(False, index=out.index)
        return col_vals.str.contains(term, na=False) | ((col_vals.str.strip() == "") & fallback)

    # Treatment type: inpatient, outpatient, residential, telehealth
    treatment = criteria.get("treatment_type")
    if treatment and ("treatment_type" in out.columns or "services" in out.columns):
        t = norm(treatment)
        out = out[col_or_services_contains("treatment_type", t)]

    # Payment: Medicaid, MassHealth, insurance, sliding scale, free, veterans
    payment = criteria.get("payment")
    if payment and ("payment_options" in out.columns or "services" in out.columns):
        p = norm(payment)
        out = out[col_or_services_contains("payment_options", p)]

    # MAT
    if criteria.get("mat") is True:
        out = out[out["mat"].apply(norm) == "yes"]

    # Populations: veterans, adolescents, LGBTQ+, pregnant women, etc.
    pop = criteria.get("populations")
    if pop and ("populations" in out.columns or "services" in out.columns):
        p = norm(pop)
        out = out[col_or_services_contains("populations", p)]

    # Languages: e.g. Spanish, Vietnamese
    lang = criteria.get("languages")
    if lang and ("languages" in out.columns or "services" in out.columns):
        l = norm(lang)
        out = out[col_or_services_contains("languages", l)]

    # Substances addressed: e.g. alcohol, opioids
    substances = criteria.get("substances")
    if substances and ("substances_addressed" in out.columns or "services" in out.columns):
        s = norm(substances)
        out = out[col_or_services_contains("substances_addressed", s)]

    # Therapies: CBT, 12-step, etc. (MAT has dedicated filter above). Search in services and description.
    therapies = criteria.get("therapies")
    if therapies:
        t = norm(therapies)
        # Normalize 12-step variants for matching
        t_alt = "12-step" if "12" in t or "twelve" in t else t
        def has_therapy(row: pd.Series) -> bool:
            svc = norm(row.get("services", ""))
            desc = norm(row.get("description", ""))
            if t == "cbt" or t_alt == "12-step":
                if t == "cbt":
                    return "cbt" in svc or "cbt" in desc
                return "12-step" in svc or "12 step" in svc or "12-step" in desc or "12 step" in desc
            return t in svc or t in desc
        out = out[out.apply(has_therapy, axis=1)]

    # Stable order so map pins and model's "1. 2. 3." list match
    sort_cols = [c for c in ("state", "city", "facility_name") if c in out.columns]
    if sort_cols:
        out = out.sort_values(by=sort_cols, na_position="last").reset_index(drop=True)
    out = out.head(limit)
    return out.to_dict(orient="records")


def get_facility_by_name(name_fragment: str, df: pd.DataFrame | None = None) -> dict[str, Any] | None:
    """Return the first facility whose name contains the given fragment (for follow-up questions)."""
    if df is None:
        df = load_facilities()
    if df.empty or not name_fragment or not name_fragment.strip():
        return None
    frag = name_fragment.lower().strip()
    for _, row in df.iterrows():
        if frag in str(row.get("facility_name", "")).lower():
            return row.to_dict()
    return None
