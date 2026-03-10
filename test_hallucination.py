#!/usr/bin/env python
"""Quick test of hallucination detection with new extraction logic."""

import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.chat import Chatbot
from src.facilities import load_facilities

def _extract_facility_names_from_text(text: str) -> list[str]:
    """Extract facility names from numbered lists only (e.g. '1. Facility Name —')."""
    if not text:
        return []
    names = set()
    # Only match clearly numbered items: "1. **Facility Name**" or "1. Facility Name —"
    lines = text.split('\n')
    for line in lines:
        # Match: "1. **Name**" or "1. Name —" or "1. Name." at start of line
        m = re.match(r"^\s*\d+\.\s*\*?\*?([A-Z][^—\*\n]*?)(?:\*?\*?|—|\s*$)", line.strip())
        if m:
            cand = m.group(1).strip()
            # Only include if it looks like a proper facility name (3+ words or has typical facility name patterns)
            words = cand.split()
            if len(cand) > 10 and len(words) >= 2:
                names.add(cand)
    return list(names)

# Load facility names
df = load_facilities()
names_ok = set()
for _, row in df.iterrows():
    n = row.get("facility_name")
    if n and str(n).strip():
        names_ok.add(str(n).strip().lower())

print(f"Loaded {len(names_ok)} facility names from database\n")

# Test the chatbot
chatbot = Chatbot()
test_msg = "I need outpatient treatment in Boston with Medicaid."

print(f"Testing: {test_msg}")
print("-" * 60)

reply, state = chatbot.get_response(test_msg, [], {"criteria": {}, "last_results": [], "last_facility_detail": None})

print("CHATBOT RESPONSE:")
print(reply)
print("\n" + "=" * 60)

# Extract facility names
extracted = _extract_facility_names_from_text(reply)
print(f"\nEXTRACTED FACILITY NAMES: {extracted}")

# Check hallucinations
hallucinated = False
for name in extracted:
    name_lower = name.lower()
    is_real = (name_lower in names_ok) or any(name_lower in db for db in names_ok) or any(db in name_lower for db in names_ok)
    print(f"  '{name}' -> Real: {is_real}")
    if not is_real:
        hallucinated = True

print(f"\nHALLUCINATED: {'YES' if hallucinated else 'NO'}")
print(f"Result count: {len(state.get('last_results', []))}")
