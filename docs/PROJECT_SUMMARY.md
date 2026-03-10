# 6.C395 Chatbot – Project Summary

## What’s Done

### 1. Chatbot (SAMHSA Treatment Locator)

- **Role:** Helps users find substance use and mental health treatment facilities in the US by conversation. No invented facilities; only real data is shown.
- **Flow (matches `samhsa_chatbot_conversation_example.txt`):**
  - **Greet / clarify:** Asks for location (state/city), treatment type (inpatient/outpatient/residential/telehealth), payment (Medicaid, insurance, sliding scale, etc.), and optionally substances, populations (veterans, LGBTQ+, adolescents), therapies (MAT, CBT, 12-step), languages.
  - **First results:** Once there’s at least a location, runs search and presents 2–3 facilities by name with short descriptions from data only.
  - **Follow-up:** If the user asks about a specific facility (“Do they offer MAT?”), answers from that facility’s record only.
  - **Closing:** Brief supportive close when the user is done.
- **Implementation:** `src/chat.py` – `Chatbot` class with criteria extraction (`_extract_criteria`), merge with prior state, search when location is present, and response via Hugging Face Inference API. System prompt enforces “use only provided facility data; never invent names/addresses/phones.”

### 2. RAG-style retrieval (no hallucination)

- **Data:** Facility records from SAMHSA (CSV: `data/facilities.csv` or a Hugging Face Dataset when `FACILITIES_DATASET` is set). Scripts: `scripts/download_findtreatment_data.py`, `scripts/ingest_facilities.py`, `scripts/upload_facilities_to_hf.py`.
- **Search:** `src/facilities.py` – `load_facilities()`, `search(criteria, df, limit)`. Criteria: state, location (city), treatment_type, payment, mat, populations, languages, substances, therapies. Returns list of facility dicts.
- **RAG pattern:** User message → extract/merge criteria → run `search()` when location exists → format results as “Current facility data” in the system prompt → LLM answers only from that context. Follow-up about a specific facility uses `get_facility_by_name()` and the same “only this data” prompt. So the model is **retrieval-grounded**: it never invents facilities.

### 3. Evaluation

- **Script:** `scripts/eval_chatbot.py`.
- **Scenarios:** 19 scenarios (e.g. “Outpatient, Boston, Medicaid”, “Veterans, Texas”, “Chicago, MAT”) with criteria dicts and sample user messages.
- **Metrics:**
  - **Match:** For each scenario, `search(criteria)` is run; each returned facility is checked against criteria (state, treatment type, payment, MAT, populations, languages, substances, therapies). Output: “all match? Y/N” and summary “X/19 runs had all suggested facilities matching criteria.”
  - **Hallucination (optional):** With `--with-chatbot`, the bot is called per scenario; facility names (and contact info) mentioned in the reply are checked against the dataset. Target: 0 invented facilities.
- **Output:** Table (default) or CSV: scenario, facilities returned, count, all_match, hallucination (if `--with-chatbot`).
- **Usage:** `python scripts/eval_chatbot.py` (search + match only); `python scripts/eval_chatbot.py --with-chatbot` (add hallucination check; needs HF token).

### 4. Maps (Gradio app)

- **UI:** `app.py` – two-pane layout: **map (left)** + **chat (right)**. Facility dropdown to pick a result; selected facility is highlighted on the map.
- **Map backends:**
  - **Google Maps:** When `GOOGLE_MAPS_API_KEY` is set in `.env`, the map is an interactive Google Maps iframe (markers, info windows, optional routes). Requires “Maps JavaScript API” and “Directions API” if you use routes.
  - **Fallback:** If no key, uses **Folium/OpenStreetMap** (Leaflet): markers, popups, optional route via OSRM.
- **Behavior:** Geocoding for facility city/state (Nominatim cache); pins for search results; optional route from user location to first facility in Folium mode; selected facility shown with a distinct icon. Map updates when the user sends a new message (new results) or changes the facility dropdown.
- **Compatibility:** Gradio version differences handled: Chatbot `type="messages"` only if supported; CSS passed to `gr.Blocks(..., css=CSS)`; `launch()` only gets supported kwargs (e.g. `theme`).

### 5. Deployment and repo hygiene

- **Hugging Face Space:** App runs on CPU; uses HF Inference for the model. Push with `git push huggingface student-version:main` (binary xlsx was removed from history so HF accepts the push). `scripts/push_to_hf.sh` runs that push.
- **Secrets:** Space needs `HF_TOKEN` (and optionally `GOOGLE_MAPS_API_KEY` if you configure it on the Space).
- **Data on Space:** Full facility CSV is large; use a Hugging Face Dataset and set `FACILITIES_DATASET` (see `data/README.md`).

---

## What’s still in progress / optional

- **Memo:** 1–2 page memo (Design, Data, Evaluation, Limitations) and optional figure (eval table or dialogue snippet) – not in repo yet.
- **Eval in memo:** Run `eval_chatbot.py` (with `--with-chatbot` if desired), paste or summarize the table in the memo.
- **Data story in repo:** Optional short `data/README.md` (or comment in `src/facilities.py`) with source (e.g. N-SUMHSS / National Directory), scope, and limitations for memo reference.
- **Accessibility / i18n:** Memo can mention keyboard use and clear labels; product is English-only for now.
- **Future API:** Backend is in `chat.py` + `facilities.py`; a thin FastAPI/Flask `POST /chat` could be added later for a React/Vercel frontend without moving core logic.

---

## What could be done next

| Area | Possible next steps |
|------|---------------------|
| **Chatbot** | Fine-tune `MY_MODEL` on example dialogues; extend criteria (e.g. more states/cities); handle “near me” with IP geolocation. |
| **RAG / data** | Add more facility attributes or filters; use embeddings + vector search instead of (or in addition to) keyword/criteria search; support data/README and dataset versioning. |
| **Evaluation** | Add more scenarios (e.g. edge cases, non-English-like prompts); automate eval in CI; track metrics over time. |
| **Maps** | Add user geolocation in the Space; improve mobile layout; optional clustering for many markers. |
| **UX** | Short “How to use” in the UI; optional language/locale; printable summary of results. |
| **DevOps** | Optional API for a React app; Docker for local run; pin Gradio version for consistent behavior. |

---

## File map

| Path | Purpose |
|------|--------|
| `app.py` | Gradio UI: map + chat, state, examples, disclaimer, theme. |
| `src/chat.py` | Chatbot: criteria extraction, search, prompt formatting, HF Inference, no hallucination. |
| `src/facilities.py` | Load CSV or HF Dataset; `search(criteria)`; column mapping. |
| `scripts/eval_chatbot.py` | 19 scenarios; match check; optional hallucination check; table/CSV output. |
| `scripts/push_to_hf.sh` | Push `student-version` to HF Space `main`. |
| `config.py` | `BASE_MODEL`, `MY_MODEL`, `HF_TOKEN`. |
| `data/README.md` | Data source, HF Dataset usage for Space. |
| `docs/MEMO.md` | Memo placeholder / notes. |
| `docs/PROJECT_SUMMARY.md` | This file. |
