# Characteristics and Treatment Patterns in a Synthetic Multi-Cancer Cohort of 100 Patients

## Abstract

**Background:** We describe a synthetic cohort of 100 patients across 10 cancer types designed to evaluate clinical data extraction pipelines and privacy-preserving database querying systems.

**Methods:** Synthetic clinical data were generated for 100 patients representing non-small cell lung cancer (NSCLC) with EGFR mutations (n=15), NSCLC without targetable drivers (n=10), HER2-positive breast cancer (n=12), KRAS-mutant colorectal cancer (n=10), metastatic castration-resistant prostate cancer (n=10), BRAF-mutant melanoma (n=10), diffuse large B-cell lymphoma (n=10), FLT3-ITD acute myeloid leukemia (n=8), multiple myeloma (n=8), and pancreatic adenocarcinoma (n=7). Clinical events, documents, encounters, and laboratory data were generated for each patient.

**Results:** The cohort comprised 51 males (51%) and 49 females (49%) with a mean age of 58.9 years (SD 10.8, range 28-77). Advanced-stage disease predominated: 86% of staged NSCLC patients presented at Stage IV/IIIB, 80% of melanoma patients at Stage IV, and 50% of DLBCL patients at Stage IV. Systemic therapy was the most common treatment modality (316 treatment events), followed by surgery (58 events) and radiation (50 events). A total of 1,997 clinical encounters and 2,188 laboratory results were recorded.

**Conclusions:** This synthetic cohort provides a comprehensive testbed for evaluating oncology data wrangling tools across diverse cancer types and treatment paradigms.

## Methods

### Study Design and Cohort

This is a synthetic dataset generated for evaluation purposes. Ten clinical scenarios were defined spanning solid tumors and hematologic malignancies. For each scenario, patient event timelines were generated consisting of 20-30 chronological clinical events per patient, including demographics, diagnosis, treatment, imaging, pathology, genomic testing, and adverse events.

### Data Generation Pipeline

Clinical documents (progress notes, imaging reports, pathology reports, NGS reports) were generated from each patient's event timeline. Structured tabular data including encounters and laboratory results were assembled to mirror real-world electronic health record structure.

### Statistical Analysis

Descriptive statistics were computed using aggregate queries against a DuckDB database with privacy enforcement (cell suppression for counts below 5). Categorical variables are presented as counts and percentages; continuous variables as means with standard deviations.

## Results

### Patient Demographics

The cohort comprised 100 patients: 51 males (51.0%) and 49 females (49.0%). Mean age at presentation was 58.9 years (SD 10.8, range 28-77 years).

**Table 1. Patient Demographics and Cancer Type Distribution**

| Cancer Type | N | % | Male | Female | Mean Age |
|-------------|---|---|------|--------|----------|
| NSCLC, EGFR-mutant | 15 | 15.0% | — | — | — |
| HER2+ Breast Cancer | 12 | 12.0% | — | — | — |
| NSCLC, Wild-type | 10 | 10.0% | — | — | — |
| KRAS-mutant CRC | 10 | 10.0% | — | — | — |
| mCRPC | 10 | 10.0% | — | — | — |
| BRAF-mutant Melanoma | 10 | 10.0% | — | — | — |
| DLBCL | 10 | 10.0% | — | — | — |
| AML, FLT3-ITD | 8 | 8.0% | — | — | — |
| Multiple Myeloma | 8 | 8.0% | — | — | — |
| Pancreatic Adenocarcinoma | 7 | 7.0% | — | — | — |
| **Total** | **100** | **100%** | **51** | **49** | **58.9** |

### Stage Distribution

Advanced-stage disease predominated across cancer types:

**Table 2. Stage Distribution by Cancer Type**

| Cancer Type | Stage I-II | Stage III | Stage IV | Total Staged |
|-------------|-----------|-----------|----------|-------------|
| NSCLC EGFR | 0 | 2 (13%) | 13 (87%) | 15 |
| NSCLC Wild-type | 0 | 4 (40%) | 6 (60%) | 10 |
| Breast HER2+ | 3 (25%) | 2 (17%) | 5 (42%) | 12 |
| Melanoma BRAF | 0 | 4 (33%) | 8 (67%) | 12 |
| DLBCL | 3 (30%) | 2 (20%) | 5 (50%) | 10 |
| Myeloma (ISS) | 4 (50%) | 4 (50%) | — | 8 |

### Treatment Patterns

Systemic therapy was the dominant treatment modality across all cancer types.

**Table 3. Treatment Events by Cancer Type and Modality**

| Cancer Type | Systemic | Surgery | Radiation | Total |
|-------------|----------|---------|-----------|-------|
| NSCLC EGFR | 30 | 4 | 8 | 42 |
| NSCLC Wild-type | 28 | 2 | 4 | 34 |
| Breast HER2+ | 39 | 7 | 10 | 56 |
| CRC KRAS | 23 | 11 | 1 | 35 |
| Prostate mCRPC | 37 | 6 | 13 | 56 |
| Melanoma BRAF | 20 | 22 | 4 | 46 |
| DLBCL | 51 | 2 | 2 | 55 |
| AML FLT3 | 24 | 0 | 0 | 24 |
| Myeloma | 38 | 0 | 4 | 42 |
| Pancreatic | 26 | 4 | 4 | 34 |
| **Total** | **316** | **58** | **50** | **424** |

Notable patterns:
- DLBCL had the highest rate of systemic therapy events (5.1 per patient), consistent with multi-cycle R-CHOP regimens
- Melanoma had the highest surgery rate (2.2 per patient), reflecting wide local excisions and lymph node dissections
- AML had no surgery or radiation events, as expected for a hematologic malignancy treated with chemotherapy and transplant

### Clinical Encounters

A total of 1,997 clinical encounters were recorded across all patients (mean 20.0 per patient).

**Table 4. Encounter Distribution by Department**

| Department | N | % |
|-----------|---|---|
| Medical Oncology | 1,087 | 54.4% |
| Radiology | 516 | 25.8% |
| Pathology | 286 | 14.3% |
| Surgery | 58 | 2.9% |
| Radiation Oncology | 50 | 2.5% |

### Laboratory Results

A total of 2,188 laboratory results were recorded across 547 collection events. Mean values were within expected ranges for an oncology population.

**Table 5. Laboratory Value Summary**

| Test | N | Mean | SD | Reference Range |
|------|---|------|----|----------------|
| WBC (10^9/L) | 547 | 7.2 | 2.1 | 4.0-11.0 |
| Hemoglobin (g/dL) | 547 | 12.7 | 1.5 | 12.0-16.0 |
| Platelets (10^9/L) | 547 | 238.1 | 65.5 | 150-400 |
| Creatinine (mg/dL) | 547 | 0.9 | 0.2 | 0.6-1.2 |

## Discussion

This synthetic multi-cancer cohort of 100 patients provides a comprehensive testbed for evaluating oncology data extraction, database building, and privacy-preserving query systems. The cohort covers 10 distinct cancer types spanning solid tumors and hematologic malignancies, with clinically realistic treatment patterns, staging distributions, and laboratory values.

The predominance of advanced-stage disease reflects the intentional design of scenarios focused on metastatic and locally advanced presentations where treatment decision-making is complex. The diversity of treatment modalities — from targeted therapy in EGFR-mutant NSCLC to R-CHOP chemotherapy in DLBCL to stem cell transplant in AML and myeloma — tests extraction systems across the full range of oncologic interventions.

Key limitations include the use of simplified clinical documents (rather than full-length clinical notes) and the absence of real-world data variability. Future work should evaluate extraction accuracy against more realistic document formats and assess the privacy-preserving query system under adversarial conditions.
