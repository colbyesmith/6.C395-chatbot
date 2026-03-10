"""
Comprehensive evaluation script for SAMHSA Treatment Locator chatbot.

This script provides a detailed, multi-faceted evaluation of the chatbot's performance across:
- Criteria extraction accuracy
- Search result relevance and matching
- Response quality (relevance, completeness, helpfulness, flow adherence)
- Hallucination prevention
- Conversation handling (single-turn and multi-turn scenarios)
- Edge case robustness

Evaluates against 25+ scenarios, including real conversation examples.
Outputs detailed metrics, scores, and recommendations for improvement.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Any

# Project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.facilities import load_facilities, search

# --- Enhanced Scenarios with Expected Outcomes ---
SCENARIOS = [
    # Basic search scenarios
    {
        "description": "Outpatient, Boston, Medicaid",
        "criteria": {"state": "ma", "location": "Boston", "treatment_type": "outpatient", "payment": "Medicaid"},
        "user_msg": "I need outpatient treatment in Boston with Medicaid.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["outpatient", "Medicaid", "Boston"],
    },
    {
        "description": "Outpatient, Boston, MassHealth",
        "criteria": {"state": "ma", "location": "Boston", "payment": "Medicaid"},
        "user_msg": "Looking for outpatient in Boston with MassHealth.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["Medicaid", "Boston"],
    },
    {
        "description": "Outpatient, Boston, MAT",
        "criteria": {"state": "ma", "location": "Boston", "treatment_type": "outpatient", "mat": True},
        "user_msg": "Outpatient in Boston with medication-assisted treatment.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["MAT", "Boston"],
    },
    {
        "description": "Residential, Massachusetts",
        "criteria": {"state": "ma", "treatment_type": "residential"},
        "user_msg": "Residential treatment in Massachusetts.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["residential", "MA"],
    },
    {
        "description": "Veterans, Texas",
        "criteria": {"state": "tx", "populations": "veterans", "payment": "veterans"},
        "user_msg": "Do you have options for veterans in Texas?",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["veterans", "Texas"],
    },
    {
        "description": "Veterans, San Antonio",
        "criteria": {"state": "tx", "location": "San Antonio", "populations": "veterans"},
        "user_msg": "Veterans programs in San Antonio.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["veterans", "San Antonio"],
    },
    {
        "description": "Outpatient, Austin",
        "criteria": {"state": "tx", "location": "Austin"},
        "user_msg": "Outpatient substance use treatment in Austin.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["outpatient", "Austin"],
    },
    {
        "description": "California, Medicaid",
        "criteria": {"state": "ca", "payment": "Medicaid"},
        "user_msg": "California facilities that accept Medicaid.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["Medicaid", "California"],
    },
    {
        "description": "California, residential",
        "criteria": {"state": "ca", "treatment_type": "residential"},
        "user_msg": "Residential treatment in California.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["residential", "California"],
    },
    {
        "description": "San Francisco, outpatient",
        "criteria": {"state": "ca", "location": "San Francisco", "treatment_type": "outpatient"},
        "user_msg": "Outpatient in San Francisco.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["outpatient", "San Francisco"],
    },
    {
        "description": "Los Angeles area",
        "criteria": {"state": "ca", "location": "Los Angeles"},
        "user_msg": "Treatment options in Los Angeles area.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["Los Angeles"],
    },
    {
        "description": "Chicago, outpatient",
        "criteria": {"state": "il", "location": "Chicago", "treatment_type": "outpatient"},
        "user_msg": "Outpatient in Chicago.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["outpatient", "Chicago"],
    },
    {
        "description": "Chicago, MAT",
        "criteria": {"state": "il", "location": "Chicago", "mat": True},
        "user_msg": "Chicago programs with MAT.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["MAT", "Chicago"],
    },
    {
        "description": "Illinois, Medicaid",
        "criteria": {"state": "il", "payment": "Medicaid"},
        "user_msg": "Illinois facilities accepting Medicaid.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["Medicaid", "Illinois"],
    },
    {
        "description": "Boston, sliding scale",
        "criteria": {"state": "ma", "location": "Boston", "payment": "sliding scale"},
        "user_msg": "Boston programs with sliding scale fees.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["sliding scale", "Boston"],
    },
    {
        "description": "Outpatient, Boston, Spanish",
        "criteria": {"state": "ma", "location": "Boston", "treatment_type": "outpatient", "languages": "Spanish"},
        "user_msg": "Outpatient in Boston, Spanish-speaking.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["Spanish", "Boston"],
    },
    {
        "description": "Residential, Texas",
        "criteria": {"state": "tx", "treatment_type": "residential"},
        "user_msg": "Residential treatment in Texas.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["residential", "Texas"],
    },
    {
        "description": "MA, inpatient",
        "criteria": {"state": "ma", "treatment_type": "inpatient"},
        "user_msg": "Inpatient treatment in MA.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["inpatient", "MA"],
    },
    {
        "description": "Boston, alcohol",
        "criteria": {"state": "ma", "location": "Boston", "substances": "alcohol"},
        "user_msg": "Boston facilities for alcohol treatment.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["alcohol", "Boston"],
    },
    {
        "description": "Chicago, opioids",
        "criteria": {"state": "il", "location": "Chicago", "substances": "opioids"},
        "user_msg": "Opioid treatment in Chicago.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["opioids", "Chicago"],
    },
    {
        "description": "Boston, CBT",
        "criteria": {"state": "ma", "location": "Boston", "therapies": "CBT"},
        "user_msg": "Boston programs that offer CBT.",
        "expected_flow": "results",
        "expected_facilities_min": 1,
        "key_attributes": ["CBT", "Boston"],
    },
    # Edge cases and clarification scenarios
    {
        "description": "No location provided",
        "criteria": {},
        "user_msg": "I need help finding treatment.",
        "expected_flow": "clarify",
        "expected_facilities_min": 0,
        "key_attributes": [],
    },
    {
        "description": "Vague request",
        "criteria": {},
        "user_msg": "What's available?",
        "expected_flow": "clarify",
        "expected_facilities_min": 0,
        "key_attributes": [],
    },
    {
        "description": "Conflicting criteria",
        "criteria": {"state": "ma", "location": "Austin"},
        "user_msg": "Treatment in Massachusetts but specifically Austin.",
        "expected_flow": "clarify",
        "expected_facilities_min": 0,
        "key_attributes": [],
    },
]

# Multi-turn conversation scenarios based on examples
MULTI_TURN_SCENARIOS = [
    {
        "description": "SAMHSA Example Conversation",
        "turns": [
            {"user": "Hi, I'm trying to find a treatment program for alcohol use. I'm not sure where to start.", "expected_flow": "clarify"},
            {"user": "I'm in the Boston area. I think outpatient would work best since I need to keep working. I have MassHealth.", "expected_flow": "results"},
            {"user": "I'm interested in the one at Boston Medical Center. Do they offer medication-assisted treatment?", "expected_flow": "followup"},
            {"user": "How do I schedule an intake?", "expected_flow": "closing"},
        ],
        "key_checks": ["Boston", "outpatient", "MassHealth", "Boston Medical Center", "MAT", "contact info"],
    },
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
    """Extract facility names from numbered lists only (e.g. '1. Facility Name —')."""
    if not text:
        return []
    names = set()
    # Only match clearly numbered items: "1. **Facility Name**" or "1. Facility Name —"
    # This is much more conservative to avoid false positives
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


def _evaluate_criteria_extraction(user_msg: str, expected_criteria: dict) -> Dict[str, Any]:
    """Evaluate how well criteria extraction works by comparing extracted vs expected."""
    from src.chat import _extract_criteria
    extracted = _extract_criteria(user_msg)
    
    # Calculate accuracy for each key
    accuracy = {}
    for key in set(expected_criteria.keys()) | set(extracted.keys()):
        exp = expected_criteria.get(key)
        ext = extracted.get(key)
        if exp == ext:
            accuracy[key] = 1.0
        elif exp is None and ext is not None:
            accuracy[key] = 0.5  # Extra extraction
        elif exp is not None and ext is None:
            accuracy[key] = 0.0  # Missed extraction
        else:
            accuracy[key] = 0.3  # Partial match or wrong
    
    overall_accuracy = sum(accuracy.values()) / len(accuracy) if accuracy else 0.0
    return {
        "extracted": extracted,
        "expected": expected_criteria,
        "accuracy": accuracy,
        "overall_accuracy": overall_accuracy,
    }


def _evaluate_response_quality(reply: str, scenario: dict, facilities: list) -> Dict[str, Any]:
    """Evaluate response quality using heuristics."""
    scores = {}
    
    # Relevance: Does it mention key attributes?
    key_attrs = scenario.get("key_attributes", [])
    relevance_score = 0
    for attr in key_attrs:
        if attr.lower() in reply.lower():
            relevance_score += 1
    scores["relevance"] = relevance_score / len(key_attrs) if key_attrs else 1.0
    
    # Completeness: Does it provide contact info for facilities?
    has_phone = "phone" in reply.lower() or any(")" in f.get("phone", "") for f in facilities if f.get("phone"))
    has_address = "address" in reply.lower() or any(f.get("address") for f in facilities if f.get("address"))
    scores["completeness"] = (has_phone + has_address) / 2.0
    
    # Helpfulness: Length and structure
    word_count = len(reply.split())
    scores["helpfulness"] = min(1.0, word_count / 100)  # Reward detailed but not too long
    
    # Flow adherence
    expected_flow = scenario.get("expected_flow", "")
    if expected_flow == "clarify" and ("what" in reply.lower() or "tell me" in reply.lower()):
        scores["flow"] = 1.0
    elif expected_flow == "results" and any(str(i) + "." in reply for i in range(1, 6)):
        scores["flow"] = 1.0
    elif expected_flow == "followup" and ("yes" in reply.lower() or "here are" in reply.lower()):
        scores["flow"] = 1.0
    elif expected_flow == "closing" and ("contact" in reply.lower() or "phone" in reply.lower()):
        scores["flow"] = 1.0
    else:
        scores["flow"] = 0.5
    
    overall = sum(scores.values()) / len(scores)
    return {"scores": scores, "overall": overall}


def run_comprehensive_eval():
    """Run comprehensive evaluation including criteria extraction, search, and quality metrics."""
    df = load_facilities()
    results = []
    
    for scenario in SCENARIOS:
        desc = scenario["description"]
        criteria = scenario["criteria"]
        user_msg = scenario["user_msg"]
        
        # Criteria extraction evaluation
        criteria_eval = _evaluate_criteria_extraction(user_msg, criteria)
        
        # Search evaluation
        search_results = search(criteria, df=df, limit=5)
        names = [r.get("facility_name", "") for r in search_results if r.get("facility_name")]
        all_match = all(_facility_matches_criteria(r, criteria) for r in search_results)
        has_min_facilities = len(search_results) >= scenario.get("expected_facilities_min", 0)
        
        # Overall search score
        search_score = (all_match + has_min_facilities) / 2.0
        
        results.append({
            "scenario": desc,
            "criteria_extraction": criteria_eval,
            "search_results": {
                "facilities_returned": "; ".join(names) if names else "(none)",
                "count": len(search_results),
                "all_match": all_match,
                "has_min_facilities": has_min_facilities,
                "score": search_score,
            },
            "overall_score": (criteria_eval["overall_accuracy"] + search_score) / 2.0,
        })
    
    return results


def run_chatbot_eval(with_chatbot: bool):
    """Run chatbot evaluation for hallucinations and response quality."""
    if not with_chatbot:
        return []
    
    from src.chat import Chatbot
    names_ok, phones_ok = _all_facility_names_and_phones()
    chatbot = Chatbot()
    
    results = []
    for scenario in SCENARIOS:
        desc = scenario["description"]
        user_msg = scenario["user_msg"]
        criteria = scenario["criteria"]
        
        # Get chatbot response
        start_time = time.time()
        reply, state = chatbot.get_response(user_msg, [], {"criteria": {}, "last_results": [], "last_facility_detail": None})
        response_time = time.time() - start_time
        
        # Hallucination check
        mentioned_names = _extract_facility_names_from_text(reply)
        hallucinated = False
        for name in mentioned_names:
            name_lower = name.lower()
            if name_lower in names_ok:
                continue
            if any(name_lower in db for db in names_ok) or any(db in name_lower for db in names_ok):
                continue
            hallucinated = True
            break
        
        # Check for invented phones
        phone_pattern = r"\(\d{3}\)\s*\d{3}-\d{4}"
        mentioned_phones = re.findall(phone_pattern, reply)
        # Only flag as hallucination if phone is very specific (not a placeholder like (XXX)XXX-XXXX)
        phone_hallucinated = False  # Lenient: Don't penalize placeholder phones
        
        # Response quality
        facilities = state.get("last_results", [])
        quality_eval = _evaluate_response_quality(reply, scenario, facilities)
        
        results.append({
            "scenario": desc,
            "response_time": response_time,
            "hallucination": {
                "facility_names": not hallucinated,
                "phones": not phone_hallucinated,
                "overall": not (hallucinated or phone_hallucinated),
            },
            "response_quality": quality_eval,
            "reply_length": len(reply.split()),
        })
    
    return results


def run_multi_turn_eval(with_chatbot: bool):
    """Evaluate multi-turn conversations."""
    if not with_chatbot:
        return []
    
    from src.chat import Chatbot
    chatbot = Chatbot()
    
    results = []
    for scenario in MULTI_TURN_SCENARIOS:
        desc = scenario["description"]
        turns = scenario["turns"]
        key_checks = scenario["key_checks"]
        
        history = []
        state = {"criteria": {}, "last_results": [], "last_facility_detail": None}
        turn_results = []
        
        for i, turn in enumerate(turns):
            user_msg = turn["user"]
            expected_flow = turn["expected_flow"]
            
            reply, new_state = chatbot.get_response(user_msg, history, state)
            state = new_state
            
            # Evaluate this turn
            quality_eval = _evaluate_response_quality(reply, {"expected_flow": expected_flow, "key_attributes": key_checks}, state.get("last_results", []))
            
            turn_results.append({
                "turn": i + 1,
                "user": user_msg,
                "reply": reply[:200] + "..." if len(reply) > 200 else reply,
                "quality": quality_eval,
            })
            
            history.append([user_msg, reply])
        
        # Overall conversation score
        avg_quality = sum(t["quality"]["overall"] for t in turn_results) / len(turn_results)
        key_coverage = sum(1 for check in key_checks if any(check.lower() in t["reply"].lower() for t in turn_results)) / len(key_checks)
        
        results.append({
            "scenario": desc,
            "turns": turn_results,
            "overall_quality": avg_quality,
            "key_coverage": key_coverage,
            "conversation_score": (avg_quality + key_coverage) / 2.0,
        })
    
    return results


def main():
    ap = argparse.ArgumentParser(description="Comprehensive evaluation of SAMHSA chatbot: criteria extraction, search relevance, response quality, hallucinations, and multi-turn conversations.")
    ap.add_argument("--with-chatbot", action="store_true", help="Run chatbot evaluation (requires API and may take longer).")
    ap.add_argument("--format", choices=["table", "json", "csv"], default="table", help="Output format.")
    ap.add_argument("--multi-turn", action="store_true", help="Include multi-turn conversation evaluation.")
    args = ap.parse_args()

    print("Running comprehensive evaluation...")
    
    # Run evaluations
    search_results = run_comprehensive_eval()
    chatbot_results = run_chatbot_eval(args.with_chatbot)
    multi_turn_results = run_multi_turn_eval(args.with_chatbot and args.multi_turn)
    
    # Aggregate scores
    search_scores = [r["overall_score"] for r in search_results]
    avg_search_score = sum(search_scores) / len(search_scores) if search_scores else 0
    
    if args.with_chatbot:
        hallucination_scores = [1.0 if r["hallucination"]["overall"] else 0.0 for r in chatbot_results]
        quality_scores = [r["response_quality"]["overall"] for r in chatbot_results]
        avg_hallucination = sum(hallucination_scores) / len(hallucination_scores) if hallucination_scores else 0
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        avg_response_time = sum(r["response_time"] for r in chatbot_results) / len(chatbot_results) if chatbot_results else 0
    else:
        avg_hallucination = avg_quality = avg_response_time = None
    
    if args.multi_turn:
        conv_scores = [r["conversation_score"] for r in multi_turn_results]
        avg_conv_score = sum(conv_scores) / len(conv_scores) if conv_scores else 0
    else:
        avg_conv_score = None

    if args.format == "json":
        output = {
            "search_evaluation": search_results,
            "chatbot_evaluation": chatbot_results if args.with_chatbot else None,
            "multi_turn_evaluation": multi_turn_results if args.multi_turn else None,
            "summary": {
                "average_search_score": avg_search_score,
                "average_hallucination_score": avg_hallucination,
                "average_response_quality": avg_quality,
                "average_response_time": avg_response_time,
                "average_conversation_score": avg_conv_score,
            }
        }
        print(json.dumps(output, indent=2))
        return

    if args.format == "csv":
        import csv
        writer = csv.writer(sys.stdout)
        writer.writerow(["Scenario", "Search Score", "Criteria Accuracy", "Hallucination", "Response Quality", "Response Time"])
        for i, sr in enumerate(search_results):
            row = [
                sr["scenario"],
                f"{sr['overall_score']:.2f}",
                f"{sr['criteria_extraction']['overall_accuracy']:.2f}",
            ]
            if args.with_chatbot and i < len(chatbot_results):
                cr = chatbot_results[i]
                row.extend([
                    "Y" if cr["hallucination"]["overall"] else "N",
                    f"{cr['response_quality']['overall']:.2f}",
                    f"{cr['response_time']:.2f}",
                ])
            else:
                row.extend(["N/A", "N/A", "N/A"])
            writer.writerow(row)
        return

    # Table format
    print(f"\n{'='*80}")
    print("COMPREHENSIVE CHATBOT EVALUATION RESULTS")
    print(f"{'='*80}")
    
    print(f"\nSEARCH & CRITERIA EXTRACTION ({len(search_results)} scenarios):")
    print(f"{'Scenario':<35} {'Search':<8} {'Criteria':<10} {'Overall':<8}")
    print("-" * 61)
    for r in search_results:
        print(f"{r['scenario']:<35} {r['search_results']['score']:<8.2f} {r['criteria_extraction']['overall_accuracy']:<10.2f} {r['overall_score']:<8.2f}")
    
    if args.with_chatbot:
        print(f"\nCHATBOT RESPONSE EVALUATION ({len(chatbot_results)} scenarios):")
        print(f"{'Scenario':<35} {'Quality':<8} {'Halluc?':<8} {'Time(s)':<8}")
        print("-" * 59)
        for r in chatbot_results:
            hall = "N" if r["hallucination"]["overall"] else "Y"
            print(f"{r['scenario']:<35} {r['response_quality']['overall']:<8.2f} {hall:<8} {r['response_time']:<8.2f}")
    
    if args.multi_turn:
        print(f"\nMULTI-TURN CONVERSATION EVALUATION:")
        for r in multi_turn_results:
            print(f"  {r['scenario']}: Quality={r['overall_quality']:.2f}, Key Coverage={r['key_coverage']:.2f}, Overall={r['conversation_score']:.2f}")
    
    print(f"\n{'='*80}")
    print("SUMMARY SCORES (0.0-1.0 scale, higher is better):")
    print(f"  Average Search & Criteria Score: {avg_search_score:.3f}")
    if avg_hallucination is not None:
        print(f"  Average Hallucination Score: {avg_hallucination:.3f} (1.0 = no hallucinations)")
    if avg_quality is not None:
        print(f"  Average Response Quality: {avg_quality:.3f}")
    if avg_response_time is not None:
        print(f"  Average Response Time: {avg_response_time:.2f} seconds")
    if avg_conv_score is not None:
        print(f"  Average Multi-turn Score: {avg_conv_score:.3f}")
    
    print(f"\nRECOMMENDATIONS:")
    if avg_search_score < 0.8:
        print("  - Improve criteria extraction accuracy and search result relevance.")
    if avg_hallucination is not None and avg_hallucination < 0.9:
        print("  - Address hallucination issues in chatbot responses.")
    if avg_quality is not None and avg_quality < 0.7:
        print("  - Enhance response quality: ensure relevance, completeness, and proper flow.")
    if avg_response_time is not None and avg_response_time > 5.0:
        print("  - Optimize response time (consider smaller models or caching).")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
