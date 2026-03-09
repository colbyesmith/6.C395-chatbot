# Facility Data – Data Story (for memo)

## Source

- **Dataset:** N-SUMHSS (National Substance Use and Mental Health Services Survey) / National Directory of Drug and Alcohol Use Treatment Facilities. This is the same data that powers [FindTreatment.gov](https://findtreatment.gov).
- **Where:** SAMHSA CBHSQ Data – [N-SUMHSS data files](https://www.samhsa.gov/data/data-we-collect/n-sumhss-national-substance-use-and-mental-health-services-survey/datafiles) (SAS/CSV). National Directory also available as Excel/PDF from [National Directories](https://www.samhsa.gov/data/data-we-collect/n-sumhss-national-substance-use-and-mental-health-services-survey/national-directories).
- **Processing:** For development and demo, `facilities.csv` may be a small subset. **To use all data from FindTreatment.gov**, run: `pip install -r requirements.txt` then `python scripts/download_findtreatment_data.py`. That script downloads the official SAMHSA National Directory (same data as FindTreatment.gov) and builds `data/facilities.csv`. Alternatively, download the Excel/CSV from SAMHSA yourself and run `python scripts/ingest_facilities.py path/to/file.xlsx -o data/facilities.csv`. The ingest script maps source columns to the internal schema; see the script and N-SUMHSS codebook for variable mapping.

## Scope

- **Geography:** Sample includes facilities in MA (Boston area), TX, CA, IL. Full N-SUMHSS covers all states.
- **Attributes:** Facility name, address, city, state, zip, phone; treatment type (inpatient, outpatient, residential, telehealth); payment options (Medicaid/MassHealth, insurance, sliding scale, free, VA); MAT (medication-assisted treatment); services; **substances addressed** (e.g. alcohol, opioids); languages; populations (e.g. adults, adolescents, veterans, LGBTQ+, pregnant women); description. The chatbot helps users describe their situation and filters by these attributes.

## Limitations

- Data as of survey/publication date; facility details (phone, hours, availability) may have changed. Always confirm with the provider or [findtreatment.gov](https://findtreatment.gov) before making decisions.

