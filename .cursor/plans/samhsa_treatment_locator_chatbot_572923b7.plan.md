---
name: SAMHSA Treatment Locator Chatbot
overview: "Build the SAMHSA Treatment Locator as a single, polished Gradio app on HuggingFace: data-grounded chatbot with conversation design matching the example, clear evaluation for the memo, trust/inclusivity and data story, and a professional Gradio UI—structured so a future React/Vercel frontend can reuse the same backend."
todos: []
isProject: false
---

# SAMHSA Treatment Locator – Gradio/HF Focus (Memo-Ready)

## Goal

Deliver one strong product: a **Gradio chatbot on HuggingFace** that helps users find treatment facilities by conversation, with **no hallucinated info**, a **memo-friendly evaluation**, and a **good-looking UI**. Design the backend so that, if time allows, a React app on Vercel can call the same logic later.

---

## 1. Core product (unchanged from before)

- **Data:** Load SAMHSA facility data (CSV from N-SUMHSS or National Directory); implement `search(criteria)` in `src/facilities.py`.
- **State:** Conversation state (criteria + last results) in Gradio; extract/merge criteria from turns; run search when location (and optionally other filters) are present.
- **Accuracy:** System prompt + only pass real search results to the model; model never invents facilities, addresses, or phones.
- **Files:** [requirements.txt](requirements.txt) (+ pandas), `data/` + CSV, [src/facilities.py](src/facilities.py), [src/chat.py](src/chat.py), [app.py](app.py), [config.py](config.py).

---

## 2. Conversation design (match the example)

Align the flow with [samhsa_chatbot_conversation_example.txt](samhsa_chatbot_conversation_example.txt):


| Phase               | Behavior                                                                                                                                                                                 |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Greet / clarify** | First message: acknowledge, then ask for location, treatment type (inpatient/outpatient/residential/telehealth), and payment (insurance, Medicaid, sliding scale, free).                 |
| **First results**   | Once we have at least location (and ideally type + payment), return 2–3 facilities by name with 1–2 sentence descriptions (from data only). Offer to give more details or other options. |
| **Follow-up**       | If user asks about a specific facility (e.g. “Do they offer MAT?”), answer from the same facility record only; offer next steps (e.g. how to contact).                                   |
| **Closing**         | If user thanks or says they’re done, brief supportive close and invite them to return.                                                                                                   |


Implementation: encode this in the **system prompt** and, if needed, short **rules** (e.g. “if no location in state, ask for location before searching”). Keep responses concise and actionable.

---

## 3. Trust and inclusivity in the product

- **Disclaimer (in UI):** In Gradio description or a static text block: *“Information is from SAMHSA data. Always verify with the facility or [findtreatment.gov](https://findtreatment.gov) before making decisions. This tool does not endorse any facility.”*
- **Tone:** Supportive, non-judgmental, clear (reflected in system prompt).
- **Memo:** In the memo, mention accessibility (e.g. keyboard use, clear labels) and any limitations (e.g. English-only for now, data as of [date]).

---

## 4. Data story (for the memo)

- **Source:** Name the dataset (e.g. N-SUMHSS 2024 or National Directory 2024), where you got it, and how you converted/processed it (e.g. “SAS → CSV, kept facilities with non-missing location”).
- **Scope:** What’s included (e.g. states covered, which attributes: treatment type, payment, populations, therapies, languages).
- **Limitations:** One or two sentences (e.g. “Data as of [date]; facility details may have changed; always confirm with the provider.”).
- **In code:** Optional `data/README.md` or a short comment in `src/facilities.py` with the same bullets so the memo can reference the repo.

---

## 5. Evaluation that’s easy to describe in the memo

- **Scenarios:** Define 15–20 test scenarios (e.g. “outpatient, Boston, Medicaid, MAT”; “veterans, California, residential”). Cover variety: locations, treatment types, payment, special populations.
- **Metrics:**
  - **Hallucination:** For each run, check that every facility name (and contact info) in the bot’s reply appears in your dataset. Target: 0 invented facilities.
  - **Match:** Check that returned facilities actually match the scenario’s criteria (e.g. accepts Medicaid, offers outpatient). Report e.g. “18/20 runs had all suggested facilities matching criteria.”
- **Artifact:** A small script (e.g. `scripts/eval_chatbot.py`) or notebook that runs these scenarios (or a subset) and outputs a table: scenario, facilities returned, hallucination? (Y/N), all match? (Y/N). Use that table (or a summary) in the memo.
- **Memo section:** “Evaluation” with method (scenarios + checks) and results (numbers + 1–2 example outcomes). Makes the “we do not provide inaccurate information” claim concrete.

---

## 6. Memo that’s easy to grade

Structure the 1–2 page memo as:

- **Design:** How the chatbot works (data → criteria extraction → search → response); why this flow; how you avoid hallucination.
- **Data:** Data story (source, scope, limitations) as above.
- **Evaluation:** Method (scenarios, hallucination + match checks) and results (table or bullet list).
- **Limitations:** 2–3 short points (e.g. data freshness, English-only, no medical advice).

Optional: one figure (e.g. table of eval results or a short dialogue snippet showing good behavior).

---

## 7. Make Gradio good-looking

- **Theme:** Use a cohesive theme, e.g. `gr.themes.Soft()` or `gr.themes.Glass()` (or a custom theme) in [app.py](app.py) so the Space doesn’t look like the default.
- **Title and description:** Clear title (e.g. “SAMHSA Treatment Locator”) and a short description: what it does, that it uses SAMHSA data, and the disclaimer (or link to it).
- **Examples:** 2–3 example prompts that mirror the conversation flow (e.g. “I’m looking for outpatient alcohol treatment in Boston with Medicaid”; “Do you have options for veterans in Texas?”).
- **Layout (optional):** If useful, use `gr.Blocks()` and place the disclaimer in a visible box above or below the chat; keep the chat as the main focus.
- **Copy:** Friendly, consistent button/label text (e.g. “Send” or “Ask”) and placeholder if applicable.

No second UI codebase; all “beautiful” effort stays in this one Gradio app.

---

## 8. Future React/Vercel (if time allows)

To make a later React app on Vercel easy:

- **Logic in one place:** Keep all “business logic” (criteria extraction, search, response generation) in Python (e.g. `src/chat.py` + `src/facilities.py`). The Gradio app in [app.py](app.py) should only call into that (e.g. `chatbot.get_response(message, history, state)`).
- **Optional API later:** If you add a small FastAPI (or Flask) wrapper that exposes a single endpoint (e.g. `POST /chat` with `{ "message": "...", "history": [...], "state": {...} }` and returns `{ "response": "...", "state": {...} }`), the same backend can serve both Gradio and a React frontend. For this phase, **no API is required**; just avoid putting critical logic inside Gradio-specific code so that a thin API layer can be added later without refactoring.

---

## File and task summary


| Item                                 | Action                                                                                                     |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| Data                                 | Add `data/` + facility CSV; optional `data/README.md` for data story                                       |
| [requirements.txt](requirements.txt) | Add `pandas`                                                                                               |
| `src/facilities.py`                  | Load CSV, `search(criteria)`, column mapping                                                               |
| [src/chat.py](src/chat.py)           | Stateful flow, system prompt (no hallucination, conversation phases), criteria + search results in context |
| [app.py](app.py)                     | State + history; theme, title, description, examples, disclaimer; pass history/state to chatbot            |
| Eval                                 | `scripts/eval_chatbot.py` or notebook: run 15–20 scenarios, record hallucination + match, output table     |
| Memo                                 | 1–2 pages: Design, Data, Evaluation, Limitations (and optional figure)                                     |


Implementation order: data → facilities.py → chat.py (with conversation design + trust in prompt) → app.py (state, UI, disclaimer) → eval script → memo.