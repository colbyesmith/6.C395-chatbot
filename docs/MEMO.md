# SAMHSA Treatment Locator Chatbot – Memo

## Design

The chatbot helps users find substance use and mental health treatment facilities in the U.S. through a conversational flow. It works as follows:

1. **Data** – Facility records are loaded from a CSV (see Data section) and stored in memory.
2. **Criteria extraction** – From each user message, the system extracts location (state or city), treatment type (inpatient, outpatient, residential, telehealth), payment (Medicaid, insurance, sliding scale, free, veterans), MAT (medication-assisted treatment), populations (e.g. veterans, adolescents, LGBTQ+, pregnant women), languages (e.g. Spanish), substances (e.g. alcohol, opioids), and therapies (e.g. CBT, 12-step).
3. **Search** – When at least a location is present, the backend runs a search over the facility data and returns only facilities that match all provided criteria.
4. **Response** – The model receives the **current conversation history** plus **only the real search results** (or a single facility record for follow-up questions). It never receives fabricated data, so it cannot invent facility names, addresses, or phone numbers. The system prompt enforces conversation phases: greet/clarify (ask for location, type, payment), first results (2–3 facilities with short descriptions), follow-up (answer from the facility record only), and closing (supportive sign-off).

This design avoids hallucination by construction: the model is restricted to describing facilities that appear in the provided data.

---

## Data

- **Source:** N-SUMHSS (National Substance Use and Mental Health Services Survey) / National Directory of Drug and Alcohol Use Treatment Facilities. Data files are available from SAMHSA CBHSQ (e.g. [N-SUMHSS data files](https://www.samhsa.gov/data/data-we-collect/n-sumhss-national-substance-use-and-mental-health-services-survey/datafiles)); the National Directory is also available as Excel/PDF from SAMHSA’s National Directories page.
- **Processing:** The app uses a CSV of facilities with non-missing location (city, state). For development and demo, the repo includes a subset; in production this can be replaced with the full N-SUMHSS export (e.g. SAS converted to CSV) using the same column mapping in `src/facilities.py`.
- **Scope:** Data is aligned with FindTreatment.gov (source: N-SUMHSS/National Directory). Attributes include facility name, address, city, state, zip, phone; treatment type; payment options; MAT; services; substances addressed; languages; populations; description. The chatbot helps users describe their situation and find facilities that match their needs (treatment type, substances, payment, special populations, therapies, languages). The sample data covers multiple states (e.g. MA, TX, CA, IL); the full dataset covers all states.
- **Limitations:** Data are as of the survey/publication date. Facility details (phone, hours, availability) may have changed. Users should always confirm with the provider or [findtreatment.gov](https://findtreatment.gov) before making decisions.

---

## Evaluation

**Method:** We defined 18 test scenarios covering a variety of locations (Boston, Texas, California, Illinois), treatment types (outpatient, residential, inpatient), payment (Medicaid, sliding scale, veterans), and special populations (veterans). For each scenario we:

1. Run the backend **search** with the scenario’s criteria and record which facilities are returned.
2. **Match check:** Verify that every returned facility satisfies the scenario’s criteria (e.g. accepts Medicaid, offers outpatient). We report how many runs had all suggested facilities matching (e.g. “18/18”).
3. **Hallucination check (optional):** When running the full chatbot with the API, we parse the bot’s reply for facility names and verify that each name appears in the dataset. Target: 0 invented facilities.

**Artifact:** The script `scripts/eval_chatbot.py` runs these scenarios and prints a table: scenario, facilities returned, count, all match? (Y/N), and (if run with `--with-chatbot`) hallucination? (Y/N). Example:

```
Scenario                                Count  All match? Hallucination?
------------------------------------------------------------------------
Outpatient, Boston, Medicaid            3      Y          N
Veterans, Texas                          1      Y          N
...
Summary: 18/18 runs had all suggested facilities matching criteria.
Hallucination: 18/18 runs had no invented facility names in the reply.
```

This table (or a summary) can be pasted into the memo or a report to make the “we do not provide inaccurate information” claim concrete.

---

## Limitations

1. **Data freshness** – Facility information is as of the source dataset date. Phone numbers, hours, and availability may have changed; users should confirm with the facility or findtreatment.gov.
2. **English-only** – The current interface and criteria extraction are in English. Expanding to other languages would require additional design and data (e.g. language attributes in the dataset).
3. **No medical advice** – The tool only helps users find facilities; it does not provide clinical or medical advice. The UI includes a disclaimer to that effect and directs users to verify information with the provider.

---

*Optional figure:* A short dialogue snippet (e.g. user asks for outpatient in Boston with Medicaid; bot returns 2–3 named facilities with descriptions from the data) or a table of evaluation results can be included to illustrate design and evaluation.
