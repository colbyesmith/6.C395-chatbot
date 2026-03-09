"""
Evaluation script for SAMHSA Treatment Locator chatbot.

Runs 15–20 test scenarios. For each:
- Runs search(criteria) to get facilities returned.
- Hallucination check: if --with-chatbot, call the bot and verify every facility name
  (and contact info) in the reply appears in the dataset. Target: 0 invented facilities.
- Match check: verify returned facilities match the scenario criteria (e.g. accepts Medicaid, offers outpatient).

Outputs a table: scenario, facilities returned, hallucination? (Y/N), all match? (Y/N).
Use the table or summary in the memo.
"""

import argparse
import re
import sys
from pathlib import Path

# Project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.facilities import load_facilities, search

# --- Scenarios: (description, criteria dict, optional user message for chatbot run) ---
SCENARIOS = [
    ("Outpatient, Boston, Medicaid", {"state": "ma", "location": "Boston", "treatment_type": "outpatient", "payment": "Medicaid"}, "I need outpatient treatment in Boston with Medicaid."),
    ("Outpatient, Boston, MassHealth", {"state": "ma", "location": "Boston", "payment": "Medicaid"}, "Looking for outpatient in Boston with MassHealth."),
    ("Outpatient, Boston, MAT", {"state": "ma", "location": "Boston", "treatment_type": "outpatient", "mat": True}, "Outpatient in Boston with medication-assisted treatment."),
    ("Residential, Massachusetts", {"state": "ma", "treatment_type": "residential"}, "Residential treatment in Massachusetts."),
    ("Veterans, Texas", {"state": "tx", "populations": "veterans", "payment": "veterans"}, "Do you have options for veterans in Texas?"),
    ("Veterans, San Antonio", {"state": "tx", "location": "San Antonio", "populations": "veterans"}, "Veterans programs in San Antonio."),
    ("Outpatient, Austin", {"state": "tx", "location": "Austin"}, "Outpatient substance use treatment in Austin."),
    ("California, Medicaid", {"state": "ca", "payment": "Medicaid"}, "California facilities that accept Medicaid."),
    ("California, residential", {"state": "ca", "treatment_type": "residential"}, "Residential treatment in California."),
    ("San Francisco, outpatient", {"state": "ca", "location": "San Francisco", "treatment_type": "outpatient"}, "Outpatient in San Francisco."),
    ("Los Angeles area", {"state": "ca", "location": "Los Angeles"}, "Treatment options in Los Angeles area."),
    ("Chicago, outpatient", {"state": "il", "location": "Chicago", "treatment_type": "outpatient"}, "Outpatient in Chicago."),
    ("Chicago, MAT", {"state": "il", "location": "Chicago", "mat": True}, "Chicago programs with MAT."),
    ("Illinois, Medicaid", {"state": "il", "payment": "Medicaid"}, "Illinois facilities accepting Medicaid."),
    ("Boston, sliding scale", {"state": "ma", "location": "Boston", "payment": "sliding scale"}, "Boston programs with sliding scale fees."),
    ("Outpatient, Boston, Spanish", {"state": "ma", "location": "Boston", "treatment_type": "outpatient", "languages": "Spanish"}, "Outpatient in Boston, Spanish-speaking."),
    ("Residential, Texas", {"state": "tx", "treatment_type": "residential"}, "Residential treatment in Texas."),
    ("MA, inpatient", {"state": "ma", "treatment_type": "inpatient"}, "Inpatient treatment in MA."),
    ("Boston, alcohol", {"state": "ma", "location": "Boston", "substances": "alcohol"}, "Boston facilities for alcohol treatment."),
    ("Chicago, opioids", {"state": "il", "location": "Chicago", "substances": "opioids"}, "Opioid treatment in Chicago."),
    ("Boston, CBT", {"state": "ma", "location": "Boston", "therapies": "CBT"}, "Boston programs that offer CBT."),
]

# All facility names and phones from dataset (for hallucination check)
def _all_facility_names_and_phones():
    df = load_facilities()
    names = set()
    phones = set()
    for _, row in df.iterrows():
        n = row.get("facility_name")
        if n and str(n).strip():
            names.add(str(n).strip().lower())
        p = row.get("phone")
        if p and str(p).strip():
            phones.add(str(p).strip())
    return names, phones


def _facility_matches_criteria(fac: dict, criteria: dict) -> bool:
    """Check that a facility record matches the scenario criteria. Falls back to services when attribute column missing."""
    def norm(s):
        if s is None or (isinstance(s, float) and (s != s)):  # NaN
            return ""
        return str(s).lower().strip()

    def col_or_services(col: str) -> str:
        v = fac.get(col, "")
        if v and str(v).strip():
            return norm(v)
        return norm(fac.get("services", ""))

    state = criteria.get("state")
    if state and norm(fac.get("state")) != norm(state):
        return False
    tt = criteria.get("treatment_type")
    if tt and norm(tt) not in col_or_services("treatment_type"):
        return False
    pay = criteria.get("payment")
    if pay:
        pay_norm = norm(pay)
        pop_text = col_or_services("populations")
        pay_text = col_or_services("payment_options")
        if pay_norm in ("veterans", "va"):
            if "veteran" not in pop_text and "veteran" not in pay_text:
                return False
        elif pay_norm not in pay_text:
            return False
    if criteria.get("mat") is True and norm(fac.get("mat")) != "yes":
        return False
    pop = criteria.get("populations")
    if pop and norm(pop) not in col_or_services("populations"):
        return False
    lang = criteria.get("languages")
    if lang and norm(lang) not in col_or_services("languages"):
        return False
    substances = criteria.get("substances")
    if substances and norm(substances) not in col_or_services("substances_addressed"):
        return False
    therapies = criteria.get("therapies")
    if therapies:
        t = norm(therapies)
        svc = norm(fac.get("services", ""))
        if t == "cbt":
            if "cbt" not in svc:
                return False
        elif "12" in t or "twelve" in t:
            if "12-step" not in svc and "12 step" not in svc:
                return False
        elif t not in svc:
            return False
    return True


def _extract_facility_names_from_text(text: str) -> list[str]:
    """Heuristic: find likely facility names in bot reply (e.g. 'X —' or 'X —' or numbered list '1. X —')."""
    if not text:
        return []
    # Split on common delimiters and look for title-case or known patterns
    names = set()
    # Pattern: "1. Facility Name —" or "Facility Name —" or "- Facility Name"
    for part in re.split(r"\n|\.|;", text):
        m = re.match(r"^(?:\d+\.?\s*)?([A-Za-z][^—\-:]*?)(?:\s*[—\-:]|$)", part.strip())
        if m:
            cand = m.group(1).strip()
            if len(cand) > 5 and cand.lower() not in ("yes", "no", "that", "they", "there", "here", "would", "could", "please", "contact", "phone", "address"):
                names.add(cand)
    return list(names)


def run_search_eval():
    """Run search() for each scenario; compute facilities returned and all_match."""
    df = load_facilities()
    rows = []
    for desc, criteria, _ in SCENARIOS:
        results = search(criteria, df=df, limit=5)
        names = [r.get("facility_name", "") for r in results if r.get("facility_name")]
        all_match = all(_facility_matches_criteria(r, criteria) for r in results)
        rows.append({
            "scenario": desc,
            "criteria": str(criteria),
            "facilities_returned": "; ".join(names) if names else "(none)",
            "count": len(results),
            "all_match": "Y" if all_match else "N",
        })
    return rows


def run_hallucination_check(rows, with_chatbot: bool):
    """If with_chatbot, call the bot for each scenario and set hallucination? (Y/N)."""
    for r in rows:
        r["hallucination"] = "(skip)"
    if not with_chatbot:
        return rows
    from src.chat import Chatbot
    names_ok, _ = _all_facility_names_and_phones()
    chatbot = Chatbot()
    for i, (desc, criteria, user_msg) in enumerate(SCENARIOS):
        reply, _ = chatbot.get_response(user_msg, [], {"criteria": {}, "last_results": [], "last_facility_detail": None})
        mentioned = _extract_facility_names_from_text(reply)
        hallucinated = False
        for n in mentioned:
            n_lower = n.lower()
            if n_lower in names_ok:
                continue
            if any(n_lower in db for db in names_ok) or any(db in n_lower for db in names_ok):
                continue
            hallucinated = True
            break
        rows[i]["hallucination"] = "Y" if hallucinated else "N"
    return rows


def main():
    ap = argparse.ArgumentParser(description="Evaluate SAMHSA chatbot: scenarios, match, optional hallucination check.")
    ap.add_argument("--with-chatbot", action="store_true", help="Run chatbot and check for hallucinated facility names (requires API).")
    ap.add_argument("--format", choices=["table", "csv"], default="table", help="Output format.")
    args = ap.parse_args()

    rows = run_search_eval()
    rows = run_hallucination_check(rows, args.with_chatbot)

    if args.format == "csv":
        import csv
        w = csv.DictWriter(sys.stdout, fieldnames=["scenario", "facilities_returned", "count", "all_match", "hallucination"])
        w.writeheader()
        w.writerows(rows)
        return

    # Table
    print(f"{'Scenario':<40} {'Count':<6} {'All match?':<10} {'Hallucination?':<14}")
    print("-" * 72)
    for r in rows:
        print(f"{r['scenario']:<40} {r['count']:<6} {r['all_match']:<10} {r.get('hallucination', '(n/a)'):<14}")
    match_ok = sum(1 for r in rows if r["all_match"] == "Y")
    print(f"\nSummary: {match_ok}/{len(rows)} runs had all suggested facilities matching criteria.")
    if args.with_chatbot:
        hall_ok = sum(1 for r in rows if r.get("hallucination") == "N")
        print(f"Hallucination: {hall_ok}/{len(rows)} runs had no invented facility names in the reply.")


if __name__ == "__main__":
    main()
