# Facility Data – Data Story (for memo)

## Source

- **Dataset:** N-SUMHSS (National Substance Use and Mental Health Services Survey) / National Directory of Drug and Alcohol Use Treatment Facilities. This is the same data that powers [FindTreatment.gov](https://findtreatment.gov).
- **Where:** SAMHSA CBHSQ Data – [N-SUMHSS data files](https://www.samhsa.gov/data/data-we-collect/n-sumhss-national-substance-use-and-mental-health-services-survey/datafiles) (SAS/CSV). National Directory also available as Excel/PDF from [National Directories](https://www.samhsa.gov/data/data-we-collect/n-sumhss-national-substance-use-and-mental-health-services-survey/national-directories).
- **Processing:** For development and demo, `facilities.csv` may be a small subset. **To use all data from FindTreatment.gov**, run: `pip install -r requirements.txt` then `python scripts/download_findtreatment_data.py`. That script downloads the official SAMHSA National Directory (same data as FindTreatment.gov) and builds `data/facilities.csv`. Alternatively, download the Excel/CSV from SAMHSA yourself and run `python scripts/ingest_facilities.py path/to/file.xlsx -o data/facilities.csv`. The ingest script maps source columns to the internal schema; see the script and N-SUMHSS codebook for variable mapping.

### Using the full CSV on Hugging Face Spaces

The full `facilities.csv` is too large to push in the Space repo. To use it on a Space:

1. **Create a Hugging Face Dataset** (not the Space repo): go to [huggingface.co/datasets](https://huggingface.co/datasets), click “Create new dataset”, name it e.g. `samhsa-facilities`, and make it public.
2. **Upload the CSV** — either run `python scripts/upload_facilities_to_hf.py YOUR_USERNAME/samhsa-facilities` from the repo root (uses [create from CSV](https://huggingface.co/docs/datasets/en/create_dataset) + `push_to_hub`), or in the dataset repo use **Files and versions** → **Add file** and upload `data/facilities.csv`.
3. **In your Space**: open the Space repo → **Settings** → **Repository secrets** or **Variables** (or in the Space’s “App” tab, **Variable and secrets**). Add a variable: name `FACILITIES_DATASET`, value `YOUR_HF_USERNAME/samhsa-facilities` (the dataset repo id).
4. Redeploy the Space. The app will load the full facilities table from the Dataset on startup (one-time download, then cached). This works on the free tier.

**If `data/facilities.csv` was already committed**, you must remove it from git history (not just the index) or Hugging Face will still reject the push. In your repo root:

```bash
# Remove the file from all commits (rewrites history)
git filter-branch --force --index-filter 'git rm --cached --ignore-unmatch data/facilities.csv' --prune-empty HEAD

# Clean up refs and gc
rm -rf .git/refs/original/
git reflog expire --expire=now --all && git gc --prune=now --aggressive

# Force push (if you already pushed this branch)
git push --force
```

Then create the dataset (see below) and set `FACILITIES_DATASET` on the Space.

## Scope

- **Geography:** Sample includes facilities in MA (Boston area), TX, CA, IL. Full N-SUMHSS covers all states.
- **Attributes:** Facility name, address, city, state, zip, phone; treatment type (inpatient, outpatient, residential, telehealth); payment options (Medicaid/MassHealth, insurance, sliding scale, free, VA); MAT (medication-assisted treatment); services; **substances addressed** (e.g. alcohol, opioids); languages; populations (e.g. adults, adolescents, veterans, LGBTQ+, pregnant women); description. The chatbot helps users describe their situation and filters by these attributes.

## Limitations

- Data as of survey/publication date; facility details (phone, hours, availability) may have changed. Always confirm with the provider or [findtreatment.gov](https://findtreatment.gov) before making decisions.

