"""
Stateful SAMHSA Treatment Locator chatbot.

Business logic: criteria extraction, search, response generation. No hallucination:
only real facility data is passed to the model. Conversation design matches
samhsa_chatbot_conversation_example.txt (greet/clarify → first results → follow-up → closing).
"""

import re
from typing import Any

from huggingface_hub import InferenceClient

from config import BASE_MODEL, HF_TOKEN, MY_MODEL
from src.facilities import get_facility_by_name, load_facilities, search

# --- Conversation state (criteria + last results for context) ---
DEFAULT_STATE = {
    "criteria": {},
    "last_results": [],
    "last_facility_detail": None,
    "selected_facility_name": None,
}

SYSTEM_PROMPT = """You are a supportive, non-judgmental assistant that helps people find substance use and mental health treatment facilities in the United States. You use only the facility information provided to you in this conversation—never invent facility names, addresses, phone numbers, or details. Your role is to help users describe their situation and find facilities that match their needs.

Conversation flow:
1. Greet / clarify: If the user has not yet given a location (state or city), ask for: (a) state or city, (b) treatment type (inpatient, outpatient, residential, telehealth), (c) payment (insurance, Medicaid/MassHealth, sliding scale, free), and as appropriate: substances they're concerned about (e.g. alcohol, opioids), special populations (veterans, LGBTQ+, adolescents, pregnant women), therapies (e.g. MAT, CBT, 12-step), and languages spoken. Do not search until you have at least a location.
2. First results: When you have at least location (and ideally type and payment), present 2–3 facilities by name with 1–2 sentence descriptions using ONLY the data in the "Current facility data" section below. For each facility, always include the phone number when available so the user can call; include address when helpful. Mention relevant attributes (payment, languages, populations, substances, therapies) when they match what the user asked for. Offer to give more details or other options.
3. Follow-up: If the user asks about a specific facility (e.g. "Do they offer MAT?" or "Tell me about Boston Medical Center"), answer ONLY from the facility record provided. When they ask how to contact or for details, give the phone number and address from the data. Offer next steps (e.g. "You can call them at [phone]").
4. Closing: If the user thanks you or says they're done, give a brief supportive close and invite them to return.

Rules:
- Never make up facility names, addresses, phones, or services. If the data does not say something, do not say it.
- The "Services" field for each facility contains the full list of what they offer (treatment types, payment options, languages, populations, therapies, etc.). Use this field when describing what a facility offers or when answering follow-up questions (e.g. "Do they offer outpatient?", "Do they take Medicaid?").
- Keep responses concise and actionable.
- Be supportive and clear. Do not give medical advice.
- If no location has been provided, ask for location before suggesting any facilities.
- When listing or describing a facility, always include contact info from the data: phone number (when present) and address so the user can reach them.
"""


def _extract_criteria(text: str) -> dict[str, Any]:
    """Extract location, treatment_type, payment, mat, populations, languages, substances, therapies from user message."""
    text_lower = (text or "").lower().strip()
    criteria = {}

    # State / city patterns
    state_abbr = re.findall(r"\b(ma|mass|massachusetts|tx|texas|ca|california|il|illinois)\b", text_lower)
    if state_abbr:
        m = {"ma": "ma", "mass": "ma", "massachusetts": "ma", "tx": "tx", "texas": "tx", "ca": "ca", "california": "ca", "il": "il", "illinois": "il"}
        criteria["state"] = m.get(state_abbr[0], state_abbr[0])
    if "boston" in text_lower:
        criteria["location"] = "Boston"
        criteria["state"] = "ma"
    if "austin" in text_lower or "san antonio" in text_lower:
        criteria["state"] = "tx"
    if "chicago" in text_lower:
        criteria["state"] = "il"
    if "san francisco" in text_lower or "los angeles" in text_lower or "california" in text_lower:
        criteria["state"] = "ca"
    if not criteria.get("state") and not criteria.get("location"):
        # Generic "location" for short state abbrev
        two_letter = re.search(r"\b([a-z]{2})\b", text_lower)
        if two_letter and two_letter.group(1) in ("ma", "tx", "ca", "il"):
            criteria["state"] = two_letter.group(1)

    # Treatment type
    if any(w in text_lower for w in ["inpatient", "residential"]):
        criteria["treatment_type"] = "inpatient" if "inpatient" in text_lower else "residential"
    elif "outpatient" in text_lower:
        criteria["treatment_type"] = "outpatient"
    elif "telehealth" in text_lower:
        criteria["treatment_type"] = "telehealth"

    # Payment
    if "medicaid" in text_lower or "masshealth" in text_lower:
        criteria["payment"] = "Medicaid"
    if "insurance" in text_lower and "payment" not in criteria:
        criteria["payment"] = "insurance"
    if "sliding scale" in text_lower:
        criteria["payment"] = "sliding scale"
    if "free" in text_lower and "payment" not in criteria:
        criteria["payment"] = "free"
    if "veteran" in text_lower or "va " in text_lower:
        criteria["payment"] = "veterans"
        criteria["populations"] = "veterans"

    # MAT
    if "mat" in text_lower or "medication-assisted" in text_lower or "medication assisted" in text_lower:
        criteria["mat"] = True

    # Populations: veterans, adolescents, LGBTQ+, pregnant women
    if "veteran" in text_lower and "populations" not in criteria:
        criteria["populations"] = "veterans"
    if "adolescent" in text_lower or "youth" in text_lower:
        criteria["populations"] = "adolescents"
    if "lgbtq" in text_lower or "lgbt" in text_lower or "queer" in text_lower:
        criteria["populations"] = "LGBTQ+"
    if "pregnant" in text_lower or "pregnancy" in text_lower:
        criteria["populations"] = "pregnant women"

    # Languages
    if "spanish" in text_lower or "spanish-speaking" in text_lower or "spanish speaking" in text_lower:
        criteria["languages"] = "Spanish"
    if "vietnamese" in text_lower:
        criteria["languages"] = "Vietnamese"
    if "mandarin" in text_lower or "chinese" in text_lower:
        criteria["languages"] = "Mandarin"
    if "bilingual" in text_lower and "languages" not in criteria:
        criteria["languages"] = "Spanish"  # common with "bilingual" in this context

    # Substances
    if "alcohol" in text_lower:
        criteria["substances"] = "alcohol"
    if "opioid" in text_lower or "opioids" in text_lower:
        criteria["substances"] = "opioids"
    if "substance use" in text_lower or "substance abuse" in text_lower and "substances" not in criteria:
        criteria["substances"] = "substance use"

    # Therapies: CBT, 12-step (MAT handled above)
    if "cbt" in text_lower or "cognitive behavioral" in text_lower:
        criteria["therapies"] = "CBT"
    if "12-step" in text_lower or "12 step" in text_lower or "twelve step" in text_lower:
        criteria["therapies"] = "12-step"

    return criteria


def _merge_criteria(existing: dict, new: dict) -> dict:
    """Merge new criteria into existing; new values override."""
    out = dict(existing)
    for k, v in new.items():
        if v is not None and v != "":
            out[k] = v
    return out


def _format_facilities_for_prompt(facilities: list[dict]) -> str:
    """Format facility list for inclusion in system context (model must only use this)."""
    if not facilities:
        return "(No facilities in context. Do not name or describe any facility not listed here.)"
    lines = []
    for i, f in enumerate(facilities, 1):
        name = f.get("facility_name", "Unknown")
        desc = f.get("description", "") or f.get("services", "")
        addr = f.get("address", "")
        city = f.get("city", "")
        state = f.get("state", "")
        phone = (f.get("phone") or "").strip() or (f.get("phone_number") or "").strip()
        mat = f.get("mat", "")
        services = f.get("services", "")
        contact = f"Phone: {phone}. " if phone else "(No phone in data). "
        contact += f"Address: {addr}, {city}, {state}." if (addr or city or state) else ""
        parts = [f"{i}. {name} — {desc} Contact: {contact} MAT: {mat}. Services: {services}."]
        for key, label in (("payment_options", "Payment"), ("substances_addressed", "Substances"), ("languages", "Languages"), ("populations", "Populations")):
            val = f.get(key, "")
            if val and str(val).strip():
                parts.append(f" {label}: {val}.")
        lines.append("".join(parts))
    return "\n".join(lines)


def _detect_numeric_facility_selection(text: str, last_results: list[dict]) -> int | None:
    """If user is selecting by number (1, 2, 3, '1.', 'option 1', 'the first one'), return 1-based index or None."""
    if not last_results or not text or not text.strip():
        return None
    text_lower = text.strip().lower()
    # "1", "1.", "option 1", "the first one", "number 1"
    for i in range(1, min(len(last_results) + 1, 10)):
        if text_lower in (str(i), f"{i}.", f"option {i}", f"number {i}"):
            return i
        if i == 1 and text_lower in ("first", "the first", "the first one"):
            return 1
        if i == 2 and text_lower in ("second", "the second one"):
            return 2
        if i == 3 and text_lower in ("third", "the third one"):
            return 3
    return None


def _detect_facility_mention(text: str, last_results: list[dict]) -> str | None:
    """If user is asking about a specific facility, return a name fragment to look up."""
    if not last_results or not text or not text.strip():
        return None
    text_lower = text.lower()
    for f in last_results:
        name = (f.get("facility_name") or "").lower()
        if name and (name in text_lower or any(word in text_lower for word in name.split() if len(word) > 3)):
            return f.get("facility_name")
    # Common patterns: "the one at X", "Boston Medical Center", "AdCare"
    if "boston medical" in text_lower or "bmc" in text_lower or "cope" in text_lower:
        return "Boston Medical Center"
    if "adcare" in text_lower:
        return "AdCare"
    if "bay cove" in text_lower:
        return "Bay Cove"
    return None


class Chatbot:
    """
    Stateful chatbot: criteria extraction, search when location present, only real data to model.
    """

    def __init__(self):
        model_id = MY_MODEL if MY_MODEL else BASE_MODEL
        self.client = InferenceClient(model=model_id, token=HF_TOKEN)
        self._df = None  # cache for facilities

    def _get_df(self):
        if self._df is None:
            self._df = load_facilities()
        return self._df

    def get_response(
        self,
        message: str,
        history: list[list[str]] | None = None,
        state: dict | None = None,
    ) -> tuple[str, dict]:
        """
        Generate response and updated state. Use only this entrypoint from Gradio (or a future API).
        """
        state = state if state is not None else dict(DEFAULT_STATE)
        history = history or []
        criteria = state.get("criteria", {})
        last_results = state.get("last_results", [])
        last_facility_detail = state.get("last_facility_detail")
        selected_facility_name = state.get("selected_facility_name")

        # Extract criteria from current message and merge
        new_criteria = _extract_criteria(message)
        criteria = _merge_criteria(criteria, new_criteria)

        # Check if user is selecting by number (e.g. "1.", "2") — use existing last_results, don't re-run search
        num_sel = _detect_numeric_facility_selection(message, last_results)
        if num_sel is not None and 1 <= num_sel <= len(last_results):
            chosen = last_results[num_sel - 1]
            last_facility_detail = chosen
            selected_facility_name = chosen.get("facility_name") or chosen.get("name")
            context_data = "Current facility data (use ONLY this for your answer):\n" + _format_facilities_for_prompt([chosen])
        else:
            # Check if user is asking about a specific facility by name
            facility_mention = _detect_facility_mention(message, last_results)
            if facility_mention:
                single = get_facility_by_name(facility_mention, self._get_df())
                if single:
                    last_facility_detail = single
                    selected_facility_name = single.get("facility_name") or single.get("name")
                    context_data = "Current facility data (use ONLY this for your answer):\n" + _format_facilities_for_prompt([single])
                else:
                    context_data = "No matching facility found in data. Say you don't have details for that facility and offer to search again or clarify."
                    last_facility_detail = None
            else:
                last_facility_detail = None
                selected_facility_name = None
                # Run search when we have at least location
                has_location = bool(criteria.get("state") or criteria.get("location"))
                if has_location:
                    results = search(criteria, df=self._get_df(), limit=5)
                    last_results = results
                    context_data = "Current facility data (suggest ONLY these; do not invent any other facility):\n" + _format_facilities_for_prompt(results)
                else:
                    context_data = "No search has been run yet (user has not provided a location). Ask for state or city, and optionally treatment type, payment, substances, populations, therapies, and languages, before suggesting facilities."
                    selected_facility_name = state.get("selected_facility_name")  # preserve when no search

        # Build messages for API: system (with context) + history + current user
        system_content = SYSTEM_PROMPT + "\n\n" + context_data

        messages = [{"role": "system", "content": system_content}]
        for pair in history:
            if len(pair) >= 2:
                messages.append({"role": "user", "content": pair[0]})
                messages.append({"role": "assistant", "content": pair[1]})
        messages.append({"role": "user", "content": message})

        response = self.client.chat.completions.create(
            model=self.client.model,
            messages=messages,
            max_tokens=800,
            temperature=0.5,
        )
        reply = (response.choices[0].message.content or "").strip()

        new_state = {
            "criteria": criteria,
            "last_results": last_results,
            "last_facility_detail": last_facility_detail,
            "selected_facility_name": selected_facility_name,
        }
        return reply, new_state
