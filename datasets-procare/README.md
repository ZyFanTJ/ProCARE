# Public RWS Dataset Bundle

Downloaded and organized on 2026-05-03 for the ProCARE paper workspace.

This bundle contains public, directly downloadable research data files that are close to the paper's real-world study (RWS) setting: clinical/health observational data, heterogeneous tables, join keys, missingness, clinical variables, treatments, outcomes, or safety-related fields. It does not include restricted datasets that require account login, credentialing, or a data-use agreement.

## Contents

| Dataset | Local folder | Main files | Verified shape | Why it is relevant |
| --- | --- | --- | --- | --- |
| UCI Diabetes 130-US Hospitals | `uci_diabetes_130_us_hospitals/` | original zip plus `extracted/diabetic_data.csv` and `IDS_mapping.csv` | 101,766 encounters, 50 columns | Real inpatient EHR-derived readmission dataset from 130 US hospitals. Useful for cohort construction, outcome definition, missingness, coded variables, and schema-grounded reporting. |
| NHANES 2017-2018 subset | `nhanes_2017_2018_subset/` | 10 official XPT tables, 10 official HTML codebooks, and CSV exports | 3,036-19,643 rows per table | Real observational population health survey with demographics, exam, blood pressure, diabetes questionnaire, labs, medical conditions, and prescription medication tables linked by `SEQN`. Useful for multi-table profiling and variable-role grounding. |
| TCGA-LIHC clinical metadata | `tcga_lihc_gdc_clinical/` | `gdc_tcga_lihc_clinical_cases.tsv` | 377 cases, 137 columns | Public liver hepatocellular carcinoma clinical data from GDC. Domain-aligned with the paper's HCC use case; includes demographics, diagnoses, treatments, vital status, and follow-up-related fields. |

Generated audit files:

- `table_shapes.tsv`: row and column counts from a read test.
- `checksums_sha256.tsv`: SHA-256 hashes and byte sizes for all files.
- `source_manifest.tsv`: source URLs, download status, and notes.

## Source Links

- UCI Diabetes 130-US hospitals: https://archive.ics.uci.edu/dataset/296/diabetes%2B130-us%2Bhospitals%2Bfor%2Byears%2B1999-2008
- UCI direct zip used here: https://archive.ics.uci.edu/static/public/296/diabetes+130-us+hospitals+for+years+1999-2008.zip
- NHANES 2017-2018 landing page: https://wwwn.cdc.gov/nchs/nhanes/continuousnhanes/default.aspx?BeginYear=2017
- NHANES data file prefix used here: https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/
- GDC TCGA-LIHC project page: https://portal.gdc.cancer.gov/projects/TCGA-LIHC
- GDC API cases endpoint used here: https://api.gdc.cancer.gov/cases

## Restricted High-Relevance Sources Not Downloaded

MIMIC-IV Demo and eICU Collaborative Research Database Demo are highly relevant EHR/ICU relational datasets, but direct file download from PhysioNet returned HTTP 403/401 in this environment. I did not include placeholder or error files in the bundle.

Useful pages if you want to download them manually with a PhysioNet account:

- MIMIC-IV Demo v2.2: https://physionet.org/content/mimic-iv-demo/2.2/
- eICU Collaborative Research Database Demo v2.0.1: https://physionet.org/content/eicu-crd-demo/2.0.1/

## Practical Use With ProCARE

Suggested first-pass benchmark mapping:

- UCI Diabetes: readmission outcome, medication/exposure proxies, subgroup cohort construction, missingness-aware reporting.
- NHANES: cross-sectional cohort studies, diabetes or cardiovascular risk analyses, lab-defined outcomes, medication exposure tables, demographic covariates.
- TCGA-LIHC: HCC survival/treatment/follow-up task design and domain-specific profile examples.

Important limitations:

- These public datasets are not replacements for the paper's private 54-sheet longitudinal HCC eCRF benchmark.
- NHANES is survey data, not longitudinal EHR.
- TCGA-LIHC is cancer research registry/clinical metadata, not routine care EHR.
- UCI Diabetes is real EHR-derived but mostly encounter-level and less relational than the paper's benchmark.
- Terms of use remain governed by the original data providers.
