#!/usr/bin/env python3
"""Generate synthetic oncology patient data for 50 patients across 10 cancer types.

Produces output in the same format as the onc_wrangler synthetic pipeline:
- Per-patient JSON files in patients/
- Combined all_documents.json
- tables/encounters.csv and tables/labs.csv
- summary.json
"""

import json
import os
import uuid
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "synthetic_patient_data"

MALE_FIRST_NAMES = [
    "James", "Robert", "Michael", "William", "David", "Richard", "Joseph",
    "Thomas", "Charles", "Daniel", "Matthew", "Anthony", "Mark", "Donald",
    "Steven", "Paul", "Andrew", "Joshua", "Kenneth", "Kevin", "Brian",
    "George", "Timothy", "Ronald", "Edward", "Jason", "Jeffrey", "Ryan",
    "Jacob", "Gary",
]
FEMALE_FIRST_NAMES = [
    "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Elizabeth", "Susan",
    "Jessica", "Sarah", "Karen", "Lisa", "Nancy", "Betty", "Margaret",
    "Sandra", "Ashley", "Dorothy", "Kimberly", "Emily", "Donna", "Michelle",
    "Carol", "Amanda", "Melissa", "Deborah", "Stephanie", "Rebecca", "Sharon",
    "Laura", "Cynthia",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
]

COMORBIDITIES = [
    "hypertension", "type 2 diabetes mellitus", "hyperlipidemia",
    "coronary artery disease", "atrial fibrillation", "COPD",
    "chronic kidney disease stage 2", "osteoarthritis",
    "gastroesophageal reflux disease", "hypothyroidism",
    "obesity", "obstructive sleep apnea", "peripheral vascular disease",
]

ALLERGIES_POOL = [
    "NKDA", "Penicillin (rash)", "Sulfa drugs (hives)",
    "Codeine (nausea)", "Iodine contrast (anaphylaxis)",
    "Latex (contact dermatitis)", "NKDA", "NKDA",
]

SMOKING_STATUS = [
    "Never smoker", "Former smoker (quit 5 years ago)",
    "Former smoker (quit 10 years ago)", "Former smoker (quit 2 years ago)",
    "Current smoker (1 ppd)", "Current smoker (0.5 ppd)",
    "Never smoker", "Never smoker",
]

ROS_POSITIVES = [
    "fatigue", "decreased appetite", "unintentional weight loss",
    "night sweats", "mild dyspnea on exertion", "intermittent nausea",
    "constipation", "mild peripheral edema", "joint pain",
    "intermittent headaches", "dizziness", "insomnia",
    "dry mouth", "mild cough", "abdominal bloating",
]

LAB_REFERENCE = {
    "WBC": {"unit": "K/uL", "range": "4.0-11.0", "low": 4.0, "high": 11.0},
    "Hemoglobin": {"unit": "g/dL", "range": "12.0-17.5", "low": 12.0, "high": 17.5},
    "Platelets": {"unit": "K/uL", "range": "150-400", "low": 150.0, "high": 400.0},
    "Creatinine": {"unit": "mg/dL", "range": "0.6-1.2", "low": 0.6, "high": 1.2},
    "BUN": {"unit": "mg/dL", "range": "7-20", "low": 7.0, "high": 20.0},
    "ALT": {"unit": "U/L", "range": "7-56", "low": 7.0, "high": 56.0},
    "AST": {"unit": "U/L", "range": "10-40", "low": 10.0, "high": 40.0},
    "Albumin": {"unit": "g/dL", "range": "3.5-5.5", "low": 3.5, "high": 5.5},
    "Total Bilirubin": {"unit": "mg/dL", "range": "0.1-1.2", "low": 0.1, "high": 1.2},
    "PT/INR": {"unit": "", "range": "0.8-1.1", "low": 0.8, "high": 1.1},
    "CEA": {"unit": "ng/mL", "range": "0.0-3.0", "low": 0.0, "high": 3.0},
    "CA-125": {"unit": "U/mL", "range": "0-35", "low": 0.0, "high": 35.0},
    "PSA": {"unit": "ng/mL", "range": "0.0-4.0", "low": 0.0, "high": 4.0},
    "CA 19-9": {"unit": "U/mL", "range": "0-37", "low": 0.0, "high": 37.0},
    "CA 15-3": {"unit": "U/mL", "range": "0-30", "low": 0.0, "high": 30.0},
    "LDH": {"unit": "U/L", "range": "140-280", "low": 140.0, "high": 280.0},
    "AFP": {"unit": "ng/mL", "range": "0.0-8.3", "low": 0.0, "high": 8.3},
    "HE4": {"unit": "pmol/L", "range": "0-140", "low": 0.0, "high": 140.0},
}

DOCUMENT_EVENT_TYPES = {"clinical_note", "imaging_report", "pathology_report", "ngs_report"}


# ---------------------------------------------------------------------------
# Scenario Definitions
# ---------------------------------------------------------------------------

SCENARIOS = [
    {
        "index": 0,
        "label": "nsclc_egfr",
        "blurb": "Stage III non-small cell lung cancer with EGFR L858R mutation",
        "icd10": "C34.11",
        "histology": "Adenocarcinoma",
        "site": "Right upper lobe of lung",
        "stage": "IIIA",
        "tnm": {"T": ["T2a", "T2b", "T3"], "N": ["N1", "N2"], "M": ["M0"]},
        "age_range": (52, 78),
        "sex_weights": (0.45, 0.55),  # M, F
        "tumor_markers": [],
        "treatments": [
            ("systemic", "Carboplatin AUC 5 + Pemetrexed 500 mg/m2 q3w x 4 cycles", "neoadjuvant chemotherapy"),
            ("surgery", "Right upper lobectomy with mediastinal lymph node dissection", "surgical resection"),
            ("systemic", "Osimertinib 80 mg daily", "adjuvant targeted therapy"),
        ],
        "alt_treatments": [
            ("radiation", "Concurrent chemoradiation 60 Gy in 30 fractions with weekly carboplatin/paclitaxel", "definitive chemoradiation"),
            ("systemic", "Durvalumab 10 mg/kg q2w x 12 months", "consolidation immunotherapy"),
        ],
        "ngs": {
            "actionable": [("EGFR", "p.L858R (c.2573T>G)", "Missense", "Exon 21")],
            "comutations": [("TP53", "p.R248W", "Missense", "Exon 7"), ("RB1", "Loss", "Deletion", "")],
            "vus": [("ATM", "p.V2424G", "VUS"), ("BRCA2", "p.K1003E", "VUS")],
            "tmb_range": (3, 10),
            "msi": "MSS",
        },
        "imaging_types": ["CT chest/abdomen/pelvis with contrast", "PET/CT", "Brain MRI with contrast"],
        "adverse_events": [
            ("nausea", "2"), ("fatigue", "2"), ("neutropenia", "3"),
            ("rash (acneiform)", "2"), ("diarrhea", "1"), ("elevated transaminases", "2"),
        ],
        "departments": ["Medical Oncology", "Thoracic Surgery", "Radiation Oncology", "Pulmonology"],
    },
    {
        "index": 1,
        "label": "breast_her2",
        "blurb": "Stage IV HER2-positive breast cancer with liver and bone metastases",
        "icd10": "C50.911",
        "histology": "Invasive ductal carcinoma",
        "site": "Left breast",
        "stage": "IV",
        "tnm": {"T": ["T2", "T3"], "N": ["N1", "N2"], "M": ["M1"]},
        "age_range": (38, 68),
        "sex_weights": (0.01, 0.99),
        "tumor_markers": ["CA 15-3"],
        "treatments": [
            ("systemic", "Docetaxel 75 mg/m2 + Trastuzumab 6 mg/kg + Pertuzumab 420 mg q3w x 6 cycles", "first-line chemotherapy with dual HER2 blockade"),
            ("systemic", "Trastuzumab 6 mg/kg + Pertuzumab 420 mg q3w maintenance", "maintenance HER2-directed therapy"),
            ("systemic", "Trastuzumab deruxtecan (T-DXd) 5.4 mg/kg q3w", "second-line HER2-directed ADC"),
        ],
        "alt_treatments": [
            ("systemic", "Tucatinib + Trastuzumab + Capecitabine", "third-line HER2-directed therapy"),
            ("radiation", "Stereotactic body radiation to liver metastasis 50 Gy in 5 fractions", "palliative SBRT"),
        ],
        "ngs": {
            "actionable": [("ERBB2", "Amplification (copy number 12)", "Amplification", "")],
            "comutations": [("PIK3CA", "p.H1047R", "Missense", "Exon 20"), ("TP53", "p.Y220C", "Missense", "Exon 6")],
            "vus": [("CHEK2", "p.I157T", "VUS"), ("PALB2", "p.L939W", "VUS")],
            "tmb_range": (2, 6),
            "msi": "MSS",
        },
        "imaging_types": ["CT chest/abdomen/pelvis with contrast", "Bone scan", "Brain MRI with contrast"],
        "adverse_events": [
            ("alopecia", "2"), ("neutropenia", "3"), ("diarrhea", "2"),
            ("fatigue", "2"), ("neuropathy", "1"), ("decreased LVEF", "2"),
        ],
        "departments": ["Medical Oncology", "Breast Surgery", "Radiation Oncology"],
    },
    {
        "index": 2,
        "label": "colon",
        "blurb": "Stage II colon cancer, microsatellite stable, status post hemicolectomy",
        "icd10": "C18.9",
        "histology": "Moderately differentiated adenocarcinoma",
        "site": "Sigmoid colon",
        "stage": "IIA",
        "tnm": {"T": ["T3", "T4a"], "N": ["N0"], "M": ["M0"]},
        "age_range": (50, 80),
        "sex_weights": (0.55, 0.45),
        "tumor_markers": ["CEA"],
        "treatments": [
            ("surgery", "Laparoscopic left hemicolectomy with lymph node dissection (22 nodes examined, 0/22 positive)", "surgical resection"),
            ("systemic", "Capecitabine 1250 mg/m2 BID days 1-14 q3w x 8 cycles", "adjuvant chemotherapy"),
        ],
        "alt_treatments": [
            ("systemic", "FOLFOX (5-FU/Leucovorin/Oxaliplatin) q2w x 12 cycles", "adjuvant chemotherapy"),
        ],
        "ngs": {
            "actionable": [("KRAS", "Wild-type", "No mutation", "")],
            "comutations": [("APC", "p.R1450* (c.4348C>T)", "Nonsense", "Exon 16"), ("TP53", "p.R175H", "Missense", "Exon 5")],
            "vus": [("SMAD4", "p.R361C", "VUS"), ("FBXW7", "p.R465H", "VUS")],
            "tmb_range": (3, 8),
            "msi": "MSS",
        },
        "imaging_types": ["CT chest/abdomen/pelvis with contrast", "PET/CT"],
        "adverse_events": [
            ("hand-foot syndrome", "2"), ("diarrhea", "2"), ("nausea", "1"),
            ("fatigue", "1"), ("neuropathy", "1"), ("neutropenia", "2"),
        ],
        "departments": ["Medical Oncology", "Colorectal Surgery", "Gastroenterology"],
    },
    {
        "index": 3,
        "label": "melanoma_braf",
        "blurb": "Stage IV melanoma with BRAF V600E mutation, lung and brain metastases",
        "icd10": "C43.9",
        "histology": "Malignant melanoma",
        "site": "Left upper back",
        "stage": "IV",
        "tnm": {"T": ["T3b", "T4a", "T4b"], "N": ["N2a", "N3"], "M": ["M1c", "M1d"]},
        "age_range": (35, 72),
        "sex_weights": (0.55, 0.45),
        "tumor_markers": ["LDH"],
        "treatments": [
            ("surgery", "Wide local excision with 2 cm margins and sentinel lymph node biopsy", "primary resection"),
            ("systemic", "Dabrafenib 150 mg BID + Trametinib 2 mg daily", "first-line BRAF/MEK-directed therapy"),
            ("radiation", "Stereotactic radiosurgery (SRS) 20 Gy single fraction to 2 brain metastases", "brain metastases treatment"),
            ("systemic", "Nivolumab 480 mg q4w + Ipilimumab 1 mg/kg q3w x 4 then Nivolumab maintenance", "second-line immunotherapy"),
        ],
        "alt_treatments": [
            ("systemic", "Pembrolizumab 200 mg q3w", "alternative first-line immunotherapy"),
        ],
        "ngs": {
            "actionable": [("BRAF", "p.V600E (c.1799T>A)", "Missense", "Exon 15")],
            "comutations": [("CDKN2A", "Loss", "Homozygous deletion", ""), ("TERT", "Promoter mutation (-124C>T)", "Promoter", "")],
            "vus": [("NF1", "p.T1556M", "VUS"), ("ARID2", "p.Q1334L", "VUS")],
            "tmb_range": (10, 40),
            "msi": "MSS",
        },
        "imaging_types": ["CT chest/abdomen/pelvis with contrast", "Brain MRI with contrast", "PET/CT"],
        "adverse_events": [
            ("pyrexia", "3"), ("rash", "2"), ("fatigue", "2"),
            ("diarrhea", "2"), ("immune-related colitis", "2"), ("immune-related hepatitis", "2"),
        ],
        "departments": ["Medical Oncology", "Dermatology", "Neurosurgery", "Radiation Oncology"],
    },
    {
        "index": 4,
        "label": "ovarian_hgsoc",
        "blurb": "Stage IIIC high-grade serous ovarian cancer with BRCA1 mutation",
        "icd10": "C56.9",
        "histology": "High-grade serous carcinoma",
        "site": "Right ovary",
        "stage": "IIIC",
        "tnm": {"T": ["T3c"], "N": ["N0", "N1"], "M": ["M0"]},
        "age_range": (45, 75),
        "sex_weights": (0.0, 1.0),
        "tumor_markers": ["CA-125", "HE4"],
        "treatments": [
            ("surgery", "Total abdominal hysterectomy, bilateral salpingo-oophorectomy, omentectomy, and optimal cytoreduction (residual disease < 1 cm)", "primary debulking surgery"),
            ("systemic", "Carboplatin AUC 6 + Paclitaxel 175 mg/m2 q3w x 6 cycles + Bevacizumab 15 mg/kg q3w", "first-line chemotherapy with anti-angiogenic"),
            ("systemic", "Olaparib 300 mg BID maintenance", "PARP inhibitor maintenance"),
        ],
        "alt_treatments": [
            ("systemic", "Niraparib 200 mg daily maintenance", "alternative PARP inhibitor maintenance"),
            ("systemic", "Carboplatin AUC 5 + Gemcitabine 1000 mg/m2 days 1,8 q3w", "second-line platinum-based chemotherapy"),
        ],
        "ngs": {
            "actionable": [("BRCA1", "p.E1836fs (c.5503delA)", "Frameshift", "Exon 22")],
            "comutations": [("TP53", "p.C176Y", "Missense", "Exon 5"), ("NF1", "p.R1947*", "Nonsense", "Exon 39")],
            "vus": [("CDK12", "p.T826A", "VUS"), ("ARID1A", "p.D1850N", "VUS")],
            "tmb_range": (2, 8),
            "msi": "MSS",
        },
        "imaging_types": ["CT chest/abdomen/pelvis with contrast", "PET/CT"],
        "adverse_events": [
            ("nausea", "2"), ("neutropenia", "3"), ("neuropathy", "2"),
            ("fatigue", "2"), ("anemia", "2"), ("thrombocytopenia", "2"),
        ],
        "departments": ["Medical Oncology", "Gynecologic Oncology"],
    },
    {
        "index": 5,
        "label": "prostate_crpc",
        "blurb": "Stage IV castration-resistant prostate cancer with bone metastases",
        "icd10": "C61",
        "histology": "Acinar adenocarcinoma, Gleason 4+5=9",
        "site": "Prostate",
        "stage": "IV",
        "tnm": {"T": ["T3a", "T3b"], "N": ["N1"], "M": ["M1b"]},
        "age_range": (60, 82),
        "sex_weights": (1.0, 0.0),
        "tumor_markers": ["PSA"],
        "treatments": [
            ("systemic", "Leuprolide 22.5 mg IM q3mo (ADT) + Enzalutamide 160 mg daily", "first-line ADT with ARPI"),
            ("systemic", "Docetaxel 75 mg/m2 q3w x 6 cycles + Prednisone 5 mg BID", "first-line chemotherapy for CRPC"),
            ("radiation", "Palliative radiation 30 Gy in 10 fractions to L3 vertebral body", "palliative bone radiation"),
            ("systemic", "Olaparib 300 mg BID", "second-line PARP inhibitor for BRCA2-mutant CRPC"),
        ],
        "alt_treatments": [
            ("systemic", "Abiraterone 1000 mg daily + Prednisone 5 mg BID", "alternative ARPI"),
            ("systemic", "Cabazitaxel 25 mg/m2 q3w", "third-line chemotherapy"),
        ],
        "ngs": {
            "actionable": [("BRCA2", "p.E1493fs (c.4478delA)", "Frameshift", "Exon 11")],
            "comutations": [("TP53", "p.R273C", "Missense", "Exon 8"), ("PTEN", "Loss", "Homozygous deletion", ""), ("AR", "Amplification", "Amplification", "")],
            "vus": [("ATM", "p.S1893R", "VUS"), ("CDK12", "p.Q1142H", "VUS")],
            "tmb_range": (2, 6),
            "msi": "MSS",
        },
        "imaging_types": ["CT chest/abdomen/pelvis with contrast", "Bone scan", "PSMA PET/CT"],
        "adverse_events": [
            ("fatigue", "2"), ("hot flashes", "1"), ("nausea", "2"),
            ("neutropenia", "3"), ("neuropathy", "1"), ("diarrhea", "1"),
        ],
        "departments": ["Medical Oncology", "Urology", "Radiation Oncology"],
    },
    {
        "index": 6,
        "label": "pancreatic",
        "blurb": "Stage IIB pancreatic ductal adenocarcinoma, borderline resectable",
        "icd10": "C25.9",
        "histology": "Pancreatic ductal adenocarcinoma",
        "site": "Head of pancreas",
        "stage": "IIB",
        "tnm": {"T": ["T2", "T3"], "N": ["N1"], "M": ["M0"]},
        "age_range": (55, 80),
        "sex_weights": (0.55, 0.45),
        "tumor_markers": ["CA 19-9"],
        "treatments": [
            ("systemic", "mFOLFIRINOX (Oxaliplatin 85 mg/m2 + Irinotecan 150 mg/m2 + Leucovorin 400 mg/m2 + 5-FU 2400 mg/m2 46h infusion) q2w x 8 cycles", "neoadjuvant chemotherapy"),
            ("surgery", "Pancreaticoduodenectomy (Whipple procedure) with portal vein resection and reconstruction", "surgical resection"),
            ("systemic", "Gemcitabine 1000 mg/m2 days 1, 8, 15 q4w x 4 cycles", "adjuvant chemotherapy"),
        ],
        "alt_treatments": [
            ("systemic", "Gemcitabine 1000 mg/m2 + Nab-paclitaxel 125 mg/m2 days 1, 8, 15 q4w", "alternative first-line"),
            ("radiation", "SBRT 33 Gy in 5 fractions to pancreatic bed", "adjuvant radiation"),
        ],
        "ngs": {
            "actionable": [("KRAS", "p.G12D (c.35G>A)", "Missense", "Exon 2")],
            "comutations": [("TP53", "p.G245S", "Missense", "Exon 7"), ("CDKN2A", "Loss", "Homozygous deletion", ""), ("SMAD4", "p.R361H", "Missense", "Exon 8")],
            "vus": [("BRCA2", "p.T3085A", "VUS"), ("PALB2", "p.L1009fs", "VUS")],
            "tmb_range": (1, 5),
            "msi": "MSS",
        },
        "imaging_types": ["CT chest/abdomen/pelvis with contrast", "MRI abdomen with contrast", "PET/CT"],
        "adverse_events": [
            ("neutropenia", "3"), ("diarrhea", "3"), ("nausea", "2"),
            ("fatigue", "2"), ("neuropathy", "2"), ("pancreatic fistula", "2"),
        ],
        "departments": ["Medical Oncology", "Hepatobiliary Surgery", "Gastroenterology"],
    },
    {
        "index": 7,
        "label": "bladder",
        "blurb": "Stage III muscle-invasive urothelial carcinoma of the bladder",
        "icd10": "C67.9",
        "histology": "High-grade urothelial carcinoma",
        "site": "Urinary bladder",
        "stage": "IIIA",
        "tnm": {"T": ["T3a", "T3b"], "N": ["N0", "N1"], "M": ["M0"]},
        "age_range": (55, 82),
        "sex_weights": (0.75, 0.25),
        "tumor_markers": [],
        "treatments": [
            ("systemic", "Cisplatin 70 mg/m2 day 1 + Gemcitabine 1000 mg/m2 days 1, 8 q3w x 4 cycles", "neoadjuvant chemotherapy"),
            ("surgery", "Radical cystectomy with bilateral pelvic lymph node dissection and ileal conduit urinary diversion", "surgical resection"),
            ("systemic", "Nivolumab 240 mg q2w x 12 months", "adjuvant immunotherapy"),
        ],
        "alt_treatments": [
            ("systemic", "Pembrolizumab 200 mg q3w", "alternative immunotherapy"),
            ("systemic", "Erdafitinib 8 mg daily (for FGFR-altered)", "targeted therapy"),
        ],
        "ngs": {
            "actionable": [("FGFR3", "p.S249C (c.746C>G)", "Missense", "Exon 7")],
            "comutations": [("TP53", "p.R282W", "Missense", "Exon 8"), ("RB1", "p.R445*", "Nonsense", "Exon 14")],
            "vus": [("ERBB2", "p.S310F", "VUS"), ("PIK3CA", "p.E545A", "VUS")],
            "tmb_range": (5, 20),
            "msi": "MSS",
        },
        "imaging_types": ["CT chest/abdomen/pelvis with contrast", "MRI pelvis with contrast", "PET/CT"],
        "adverse_events": [
            ("nausea", "2"), ("nephrotoxicity", "1"), ("fatigue", "2"),
            ("neutropenia", "3"), ("immune-related rash", "2"), ("immune-related thyroiditis", "1"),
        ],
        "departments": ["Medical Oncology", "Urology", "Radiation Oncology"],
    },
    {
        "index": 8,
        "label": "renal_cc",
        "blurb": "Stage IV clear cell renal cell carcinoma with lung metastases",
        "icd10": "C64.9",
        "histology": "Clear cell renal cell carcinoma, Fuhrman grade 3",
        "site": "Right kidney",
        "stage": "IV",
        "tnm": {"T": ["T3a", "T3b"], "N": ["N0"], "M": ["M1"]},
        "age_range": (48, 75),
        "sex_weights": (0.65, 0.35),
        "tumor_markers": [],
        "treatments": [
            ("surgery", "Right radical nephrectomy with adrenalectomy", "cytoreductive nephrectomy"),
            ("systemic", "Pembrolizumab 200 mg q3w + Axitinib 5 mg BID", "first-line immunotherapy-TKI combination"),
            ("systemic", "Nivolumab 240 mg q2w + Cabozantinib 40 mg daily", "second-line immunotherapy-TKI"),
        ],
        "alt_treatments": [
            ("systemic", "Sunitinib 50 mg daily (4 weeks on, 2 weeks off)", "alternative first-line TKI"),
            ("systemic", "Everolimus 10 mg daily", "mTOR inhibitor"),
        ],
        "ngs": {
            "actionable": [("VHL", "p.L89P (c.266T>C)", "Missense", "Exon 1")],
            "comutations": [("PBRM1", "p.Q1298*", "Nonsense", "Exon 24"), ("BAP1", "Loss", "Deletion", ""), ("SETD2", "p.R1740*", "Nonsense", "Exon 11")],
            "vus": [("KDM5C", "p.A388T", "VUS"), ("MTOR", "p.S2215Y", "VUS")],
            "tmb_range": (2, 8),
            "msi": "MSS",
        },
        "imaging_types": ["CT chest/abdomen/pelvis with contrast", "MRI abdomen with contrast", "Bone scan"],
        "adverse_events": [
            ("hypertension", "2"), ("fatigue", "2"), ("diarrhea", "2"),
            ("hand-foot syndrome", "2"), ("proteinuria", "1"), ("immune-related thyroiditis", "2"),
        ],
        "departments": ["Medical Oncology", "Urology"],
    },
    {
        "index": 9,
        "label": "head_neck_scc",
        "blurb": "Stage III HPV-positive squamous cell carcinoma of the oropharynx",
        "icd10": "C10.9",
        "histology": "Squamous cell carcinoma, p16-positive (HPV-associated)",
        "site": "Base of tongue",
        "stage": "III",
        "tnm": {"T": ["T2", "T3"], "N": ["N1", "N2a"], "M": ["M0"]},
        "age_range": (45, 70),
        "sex_weights": (0.80, 0.20),
        "tumor_markers": [],
        "treatments": [
            ("systemic", "Cisplatin 100 mg/m2 q3w x 3 cycles concurrent with radiation", "definitive concurrent chemoradiation"),
            ("radiation", "IMRT 70 Gy in 35 fractions to primary site and involved nodes, 56 Gy to elective nodal volumes", "definitive radiation"),
        ],
        "alt_treatments": [
            ("systemic", "Cetuximab 400 mg/m2 loading then 250 mg/m2 weekly x 7 concurrent with radiation", "bioradiation"),
            ("systemic", "Pembrolizumab 200 mg q3w + Cisplatin + 5-FU", "first-line for recurrent/metastatic"),
        ],
        "ngs": {
            "actionable": [("HPV", "HPV-16 positive (p16 IHC positive)", "Viral", "")],
            "comutations": [("PIK3CA", "p.E545K", "Missense", "Exon 9"), ("NOTCH1", "p.P2164fs", "Frameshift", "Exon 34")],
            "vus": [("CASP8", "p.R127*", "VUS"), ("FAT1", "p.G4551S", "VUS")],
            "tmb_range": (3, 10),
            "msi": "MSS",
        },
        "imaging_types": ["CT neck with contrast", "PET/CT", "MRI neck with contrast"],
        "adverse_events": [
            ("mucositis", "3"), ("dysphagia", "3"), ("xerostomia", "2"),
            ("nausea", "2"), ("nephrotoxicity", "1"), ("dermatitis", "2"),
        ],
        "departments": ["Medical Oncology", "Radiation Oncology", "Head and Neck Surgery", "Speech Pathology"],
    },
]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def make_patient_id():
    return f"patient_{uuid.uuid4().hex[:12]}"


def pick(rng, items):
    """Pick a random item from a list."""
    return items[rng.integers(0, len(items))]


def pick_n(rng, items, n):
    """Pick n unique items from a list (without replacement)."""
    n = min(n, len(items))
    indices = rng.choice(len(items), size=n, replace=False)
    return [items[i] for i in indices]


def rand_date_offset(rng, lo, hi):
    """Random integer in [lo, hi]."""
    return int(rng.integers(lo, hi + 1))


def format_date(base_date, day_offset):
    return (base_date + timedelta(days=int(day_offset))).strftime("%Y-%m-%d")


def abnormal_flag(value, ref):
    """Determine abnormal flag based on value and reference range."""
    if value < ref["low"]:
        return "L"
    elif value > ref["high"]:
        return "H"
    return "N"


def clamp(val, lo, hi):
    return max(lo, min(hi, val))


# ---------------------------------------------------------------------------
# Event text generators
# ---------------------------------------------------------------------------

def gen_demographics_text(name, age, sex, rng):
    race = pick(rng, ["White", "Black", "Hispanic", "Asian", "Other"])
    smoking = pick(rng, SMOKING_STATUS)
    return (
        f"{name}, {age}-year-old {race} {sex.lower()}, {smoking}. "
        f"Lives independently. ECOG performance status 1."
    )


def gen_diagnosis_text(scenario, tnm_vals, rng):
    t, n, m = tnm_vals
    return (
        f"Diagnosed with {scenario['histology']} of the {scenario['site']}. "
        f"Clinical staging: {t}{n}{m}, AJCC Stage {scenario['stage']}. "
        f"ICD-10: {scenario['icd10']}. {scenario['blurb']}."
    )


def gen_systemic_text(drug_info, cycle_num=None):
    _, drug, intent = drug_info
    cycle_str = f" Cycle {cycle_num}." if cycle_num else ""
    return f"Initiated {intent}: {drug}.{cycle_str} Patient tolerated treatment without immediate complications."


def gen_surgery_text(drug_info, rng):
    _, procedure, intent = drug_info
    ebl = pick(rng, ["150 mL", "200 mL", "300 mL", "250 mL", "400 mL"])
    los = pick(rng, ["3 days", "4 days", "5 days", "6 days", "7 days"])
    return (
        f"Underwent {intent}: {procedure}. "
        f"Estimated blood loss {ebl}. Length of stay {los}. "
        f"Uncomplicated postoperative course."
    )


def gen_radiation_text(drug_info):
    _, details, intent = drug_info
    return f"Completed {intent}: {details}. Treatment delivered as planned."


def gen_adverse_event_text(ae_name, grade, rng):
    management = {
        "neutropenia": "Treated with G-CSF (filgrastim 5 mcg/kg daily x 5 days). CBC monitored closely.",
        "nausea": "Managed with ondansetron 8 mg q8h PRN and dexamethasone 4 mg daily.",
        "fatigue": "Activity modification recommended. TSH and CBC checked - within normal limits.",
        "rash": "Treated with topical triamcinolone 0.1% cream BID and oral cetirizine 10 mg daily.",
        "rash (acneiform)": "Treated with doxycycline 100 mg BID and topical clindamycin gel.",
        "diarrhea": "Managed with loperamide 4 mg then 2 mg after each loose stool. Stool studies negative.",
        "neuropathy": "Dose reduction of neurotoxic agent by 25%. Gabapentin 300 mg TID started.",
        "hand-foot syndrome": "Urea-based emollient prescribed. Dose reduction per protocol.",
        "alopecia": "Counseled on expected hair regrowth post-treatment.",
        "decreased LVEF": "LVEF decreased to 48% on echocardiogram. Cardiology consulted. ACE inhibitor initiated.",
        "mucositis": "Magic mouthwash (lidocaine/diphenhydramine/Maalox) QID. PEG tube placed for nutritional support.",
        "dysphagia": "Speech pathology evaluation. Modified diet consistency. PEG tube nutrition supplementation.",
        "xerostomia": "Pilocarpine 5 mg TID initiated. Artificial saliva recommended.",
        "nephrotoxicity": "Aggressive IV hydration. Creatinine monitored. Dose adjustment per CrCl.",
        "pyrexia": "Blood cultures drawn. Empiric antibiotics held as cultures negative. Managed with acetaminophen.",
        "immune-related colitis": "Prednisone 1 mg/kg initiated. Colonoscopy showed mild colitis. Immunotherapy held.",
        "immune-related hepatitis": "ALT/AST elevated to 5x ULN. Prednisone 1 mg/kg started. Immunotherapy held.",
        "immune-related rash": "Topical clobetasol 0.05% BID. Mild, no need for systemic steroids.",
        "immune-related thyroiditis": "TSH elevated to 12.5. Levothyroxine 50 mcg daily started.",
        "hypertension": "Amlodipine 5 mg daily initiated. Blood pressure monitoring twice daily.",
        "proteinuria": "24-hour urine protein 1.2 g. Monitoring continued. No dose modification needed.",
        "elevated transaminases": "ALT 95 U/L, AST 78 U/L. Treatment held one week, then resumed at reduced dose.",
        "hot flashes": "Venlafaxine 37.5 mg daily started. Counseled on lifestyle modifications.",
        "pancreatic fistula": "Jackson-Pratt drain output monitored. Amylase-rich fluid. Conservative management.",
        "anemia": "Hemoglobin 8.5 g/dL. Transfused 2 units pRBC. Iron studies checked.",
        "thrombocytopenia": "Platelets 65 K/uL. Dose delayed one week. Recovered to 120 K/uL.",
        "dermatitis": "Grade 2 radiation dermatitis. Aquaphor and silver sulfadiazine cream applied.",
    }
    mgmt = management.get(ae_name, "Managed per institutional guidelines. Patient monitored closely.")
    return f"Developed grade {grade} {ae_name}. {mgmt}"


# ---------------------------------------------------------------------------
# Document generators
# ---------------------------------------------------------------------------

def gen_pathology_report(patient_name, patient_id, scenario, diag_date, rng):
    spec_id = f"S{diag_date[:4]}-{rng.integers(10000, 99999)}"
    size = round(rng.uniform(1.5, 8.0), 1)
    margins = pick(rng, ["Negative (closest margin 0.5 cm)", "Negative (closest margin 1.2 cm)", "Positive at inked margin", "Negative (closest margin 0.3 cm)"])
    lvi = pick(rng, ["Present", "Not identified", "Not identified", "Present"])
    pni = pick(rng, ["Present", "Not identified", "Not identified", "Not identified"])
    grade = pick(rng, ["well differentiated", "moderately differentiated", "poorly differentiated"])

    ihc_sections = {
        "nsclc_egfr": "TTF-1: Positive\nNapsin-A: Positive\nCK7: Positive\nCK20: Negative\nPD-L1 (22C3): TPS 40%",
        "breast_her2": "ER: Negative (0%)\nPR: Negative (0%)\nHER2 IHC: 3+ (positive)\nKi-67: 45%",
        "colon": "CDX2: Positive\nCK20: Positive\nCK7: Negative\nMLH1: Intact\nMSH2: Intact\nMSH6: Intact\nPMS2: Intact",
        "melanoma_braf": "S-100: Positive\nHMB-45: Positive\nMelan-A: Positive\nSOX10: Positive\nKi-67: 30%",
        "ovarian_hgsoc": "PAX8: Positive\nWT1: Positive\nP53: Aberrant (overexpression)\nCK7: Positive\nCK20: Negative",
        "prostate_crpc": "PSA: Positive\nNKX3.1: Positive\nAR: Positive\nERG: Positive (TMPRSS2-ERG fusion likely)",
        "pancreatic": "CK7: Positive\nCK20: Negative\nMUC1: Positive\nCDX2: Negative\nSMAD4: Lost (absent staining)",
        "bladder": "CK7: Positive\nCK20: Positive (focal)\nGATA3: Positive\np63: Positive\nCK5/6: Positive (focal)",
        "renal_cc": "PAX8: Positive\nCA-IX: Positive (diffuse membranous)\nCD10: Positive\nCK7: Negative\nVimentin: Positive",
        "head_neck_scc": "p16: Positive (strong, diffuse)\np63: Positive\nCK5/6: Positive\nEBV: Negative",
    }
    ihc = ihc_sections.get(scenario["label"], "Standard panel performed.")

    return f"""PATHOLOGY REPORT

Patient: {patient_name}
MRN: {patient_id}
Specimen ID: {spec_id}
Date of Procedure: {diag_date}
Date of Report: {format_date(date.fromisoformat(diag_date), rand_date_offset(rng, 2, 5))}

SPECIMEN: {scenario['site']}, excision/biopsy

FINAL DIAGNOSIS:
{scenario['histology']}, {grade}.
Greatest tumor dimension: {size} cm
Margins: {margins}
Lymphovascular invasion: {lvi}
Perineural invasion: {pni}

IMMUNOHISTOCHEMISTRY:
{ihc}

GROSS DESCRIPTION:
Received fresh labeled "{patient_name} - {scenario['site']}" is a {pick(rng, ['tan-white', 'tan-pink', 'gray-white', 'firm tan'])} tissue fragment measuring {size} x {round(size*0.7, 1)} x {round(size*0.5, 1)} cm. The cut surface reveals a {pick(rng, ['firm', 'soft', 'friable', 'indurated'])} {pick(rng, ['white', 'tan', 'gray-white', 'yellow-tan'])} mass. Specimen entirely submitted in cassettes A1-A{rng.integers(4, 12)}.

MICROSCOPIC DESCRIPTION:
Sections show a {grade} neoplasm composed of {pick(rng, ['sheets', 'nests', 'glands', 'cords and trabeculae'])} of atypical cells with {pick(rng, ['moderate', 'scant', 'abundant'])} cytoplasm and {pick(rng, ['prominent nucleoli', 'irregular nuclear contours', 'high nuclear-to-cytoplasmic ratio', 'vesicular chromatin'])}. Mitotic figures are {pick(rng, ['frequent (12 per 10 HPF)', 'identified (6 per 10 HPF)', 'occasionally seen (3 per 10 HPF)'])}. {pick(rng, ['Necrosis is present.', 'Focal necrosis is present.', 'No necrosis is identified.'])} The surrounding stroma shows {pick(rng, ['desmoplastic reaction', 'chronic inflammation', 'fibrosis', 'minimal reactive changes'])}.

Electronically signed by: {pick(rng, ['Sarah Chen, MD', 'Michael Torres, MD', 'Patricia Williams, MD', 'James Park, MD', 'Emily Nakamura, MD'])}
Department of Pathology"""


def gen_imaging_report(patient_name, patient_id, scenario, img_date, img_type, event_context, rng):
    """Generate a realistic imaging report."""
    is_baseline = "baseline" in event_context.lower() or "staging" in event_context.lower() or "initial" in event_context.lower()
    is_followup = "follow" in event_context.lower() or "surveillance" in event_context.lower() or "restaging" in event_context.lower()
    is_progression = "progression" in event_context.lower()

    comparison = "None available." if is_baseline else pick(rng, [
        f"Comparison made to prior study from approximately {rng.integers(2,4)} months ago.",
        f"Prior study dated approximately {rng.integers(6,12)} weeks ago available for comparison.",
    ])

    # Build findings based on cancer type and context
    findings_parts = []

    if "CT" in img_type or "PET" in img_type:
        # Lungs
        if scenario["label"] == "nsclc_egfr":
            size = round(rng.uniform(2.5, 5.5), 1)
            if is_followup and not is_progression:
                size = round(size * 0.6, 1)
            findings_parts.append(
                f"LUNGS: {pick(rng, ['Spiculated', 'Irregular'])} mass in the {scenario['site'].lower()} "
                f"measuring {size} x {round(size*0.8,1)} cm. "
                f"{'Decreased in size compared to prior.' if is_followup and not is_progression else 'New finding.' if is_baseline else 'Increased in size compared to prior.'}"
            )
        elif scenario["label"] in ("renal_cc", "breast_her2", "melanoma_braf"):
            if rng.random() > 0.3:
                n_mets = rng.integers(2, 6) if is_progression else rng.integers(1, 3)
                findings_parts.append(
                    f"LUNGS: {'Multiple' if n_mets > 2 else 'Few'} pulmonary nodules, largest measuring "
                    f"{round(rng.uniform(0.5, 2.0),1)} cm in the {pick(rng, ['right lower', 'left lower', 'right upper', 'left upper'])} lobe. "
                    f"{'Consistent with metastatic disease.' if is_baseline else 'Stable in size.' if not is_progression else 'Interval increase in size and number.'}"
                )
        else:
            findings_parts.append("LUNGS: Clear. No pulmonary nodules or masses. No pleural effusion.")

        # Mediastinum
        if scenario["label"] == "nsclc_egfr":
            findings_parts.append(
                f"MEDIASTINUM: {pick(rng, ['Subcarinal', 'Right hilar', 'Paratracheal'])} lymphadenopathy, "
                f"largest node measuring {round(rng.uniform(1.2, 2.5),1)} cm in short axis."
            )
        else:
            findings_parts.append("MEDIASTINUM: No significant lymphadenopathy. Heart size normal.")

        # Liver
        if scenario["label"] == "breast_her2":
            n_mets = rng.integers(2, 5)
            findings_parts.append(
                f"LIVER: {n_mets} hypodense lesions consistent with metastases, largest in "
                f"{pick(rng, ['segment 6', 'segment 7', 'segment 4a', 'segment 8'])} measuring "
                f"{round(rng.uniform(1.5, 4.0),1)} cm. "
                f"{'New finding.' if is_baseline else 'Decreased in size.' if not is_progression else 'Interval enlargement.'}"
            )
        elif scenario["label"] == "pancreatic":
            findings_parts.append(
                f"LIVER: {'No hepatic metastases identified.' if not is_progression else 'New hypodense lesion in segment 7 measuring 1.2 cm, suspicious for metastasis.'}"
            )
        else:
            findings_parts.append("LIVER: Homogeneous attenuation. No focal lesions.")

        # Pancreas
        if scenario["label"] == "pancreatic":
            size = round(rng.uniform(2.5, 4.5), 1)
            findings_parts.append(
                f"PANCREAS: Hypodense mass in the head of the pancreas measuring {size} x {round(size*0.7,1)} cm "
                f"with {'abutment' if rng.random() > 0.5 else 'encasement'} of the {pick(rng, ['SMV', 'portal vein', 'SMA'])}. "
                f"{'Pancreatic duct dilated to 6 mm.' if rng.random() > 0.3 else 'Mild upstream pancreatic duct dilation.'}"
            )
        else:
            findings_parts.append("PANCREAS: Normal in size and attenuation. No pancreatic mass or ductal dilation.")

        # Kidneys
        if scenario["label"] == "renal_cc":
            size = round(rng.uniform(5.0, 10.0), 1)
            findings_parts.append(
                f"KIDNEYS: {pick(rng, ['Heterogeneously enhancing', 'Solid enhancing'])} mass arising from the "
                f"{scenario['site'].lower()} measuring {size} x {round(size*0.8,1)} cm "
                f"{'with extension into the renal vein' if rng.random() > 0.5 else 'confined to the renal parenchyma'}."
            )
        else:
            findings_parts.append("KIDNEYS: Normal in size bilaterally. No hydronephrosis or renal masses.")

        # Pelvis
        if scenario["label"] == "ovarian_hgsoc":
            findings_parts.append(
                f"PELVIS: Complex cystic and solid mass in the {'right' if 'Right' in scenario['site'] else 'left'} adnexa "
                f"measuring {round(rng.uniform(5.0, 12.0),1)} cm. Omental caking present. "
                f"Moderate ascites. Peritoneal carcinomatosis."
            )
        elif scenario["label"] == "bladder":
            findings_parts.append(
                f"PELVIS: Irregular enhancing mass along the {pick(rng, ['posterior', 'lateral', 'dome'])} wall of the bladder "
                f"measuring {round(rng.uniform(3.0, 6.0),1)} cm with {pick(rng, ['likely', 'possible'])} extravesical extension."
            )
        elif scenario["label"] == "prostate_crpc":
            findings_parts.append(
                f"PELVIS: Enlarged prostate measuring {round(rng.uniform(4.5, 7.0),1)} cm. "
                f"Bilateral pelvic lymphadenopathy, largest node {round(rng.uniform(1.5, 3.0),1)} cm."
            )
        else:
            findings_parts.append("PELVIS: No pelvic mass or lymphadenopathy. Bladder unremarkable.")

        # Bones
        if scenario["label"] in ("prostate_crpc", "breast_her2"):
            findings_parts.append(
                f"BONES: Multiple {pick(rng, ['sclerotic', 'mixed lytic-sclerotic', 'lytic'])} osseous lesions "
                f"involving {pick(rng, ['lumbar spine, pelvis, and bilateral proximal femora', 'thoracic and lumbar spine', 'pelvis and bilateral iliac bones'])} "
                f"consistent with osseous metastatic disease."
            )
        elif scenario["label"] == "melanoma_braf" and rng.random() > 0.5:
            findings_parts.append("BONES: Lytic lesion in L2 vertebral body measuring 1.5 cm. Suspicious for metastasis.")
        else:
            findings_parts.append("BONES: No suspicious osseous lesions. Degenerative changes of the lumbar spine.")

    elif "MRI" in img_type and "Brain" in img_type:
        if scenario["label"] == "melanoma_braf":
            n_mets = rng.integers(1, 4)
            locations = pick_n(rng, ["right frontal lobe", "left parietal lobe", "right cerebellum", "left occipital lobe", "right temporal lobe"], n_mets)
            lesion_descs = [f"{loc} ({round(rng.uniform(0.5, 2.5),1)} cm)" for loc in locations]
            findings_parts.append(
                f"BRAIN: {n_mets} enhancing {'lesion' if n_mets == 1 else 'lesions'} identified: {', '.join(lesion_descs)}. "
                f"Surrounding vasogenic edema. No midline shift."
            )
        else:
            findings_parts.append("BRAIN: No intracranial mass, hemorrhage, or acute infarct. Ventricles normal in size.")

    elif "Bone scan" in img_type:
        if scenario["label"] in ("prostate_crpc", "breast_her2"):
            findings_parts.append(
                f"Multiple foci of increased radiotracer uptake in the {pick(rng, ['axial and appendicular skeleton', 'axial skeleton', 'pelvis and lumbar spine'])} "
                f"consistent with widespread osseous metastatic disease. Approximately {rng.integers(5, 15)} lesions identified."
            )
        else:
            findings_parts.append("No scintigraphic evidence of osseous metastatic disease. Degenerative uptake in bilateral knees.")

    elif "neck" in img_type.lower():
        if scenario["label"] == "head_neck_scc":
            size = round(rng.uniform(2.0, 4.5), 1)
            findings_parts.append(
                f"OROPHARYNX: Enhancing mass centered in the {scenario['site'].lower()} measuring {size} x {round(size*0.7,1)} cm "
                f"with extension to the {pick(rng, ['ipsilateral tonsil', 'soft palate', 'vallecula'])}.\n"
                f"NECK: Level {pick(rng, ['IIA', 'IIB', 'III'])} lymphadenopathy on the {'left' if rng.random() > 0.5 else 'right'}, "
                f"largest node {round(rng.uniform(1.5, 3.0),1)} cm with {'necrotic center' if rng.random() > 0.5 else 'heterogeneous enhancement'}."
            )
        else:
            findings_parts.append("NECK: No mass or pathologic lymphadenopathy identified.")

    findings_text = "\n\n".join(findings_parts) if findings_parts else "Unremarkable examination."

    # Impression
    impression_items = []
    if scenario["label"] == "nsclc_egfr":
        impression_items.append(f"1. Right upper lobe mass consistent with primary lung malignancy, {'decreased' if is_followup and not is_progression else 'stable' if is_followup else 'as described'}.")
        impression_items.append("2. Mediastinal lymphadenopathy, likely nodal metastatic disease.")
    elif scenario["label"] == "breast_her2":
        impression_items.append("1. Known breast malignancy with hepatic and osseous metastases.")
        impression_items.append(f"2. Liver lesions {'decreased in size, partial response' if is_followup and not is_progression else 'as described' if is_baseline else 'increased in size, progressive disease'}.")
    elif scenario["label"] == "melanoma_braf":
        impression_items.append("1. Brain metastases as described. Recommend neurosurgical consultation.")
        impression_items.append("2. Pulmonary nodules consistent with metastatic disease.")
    elif scenario["label"] == "ovarian_hgsoc":
        impression_items.append("1. Complex adnexal mass with peritoneal carcinomatosis and ascites, concerning for advanced ovarian malignancy.")
    elif scenario["label"] == "prostate_crpc":
        impression_items.append("1. Widespread osseous metastatic disease.")
        impression_items.append("2. Pelvic lymphadenopathy consistent with nodal metastases.")
    elif scenario["label"] == "pancreatic":
        impression_items.append(f"1. Pancreatic head mass {'with vascular involvement' if rng.random() > 0.3 else 'abutting the SMV'}. Borderline resectable.")
    elif scenario["label"] == "renal_cc":
        impression_items.append(f"1. Right renal mass consistent with renal cell carcinoma. Pulmonary metastases.")
    elif scenario["label"] == "bladder":
        impression_items.append("1. Bladder mass with suspected extravesical extension. Muscle-invasive disease suspected.")
    elif scenario["label"] == "head_neck_scc":
        impression_items.append("1. Oropharyngeal mass with cervical lymphadenopathy. Clinical staging consistent with Stage III.")
    else:
        impression_items.append(f"1. Findings consistent with {scenario['histology'].lower()} as described.")

    if not is_baseline:
        if is_progression:
            impression_items.append(f"{len(impression_items)+1}. Overall assessment: Progressive disease per RECIST 1.1.")
        else:
            impression_items.append(f"{len(impression_items)+1}. Overall assessment: {'Partial response' if rng.random() > 0.4 else 'Stable disease'} per RECIST 1.1.")

    return f"""{img_type.upper()} REPORT

Patient: {patient_name}
MRN: {patient_id}
Date of Study: {img_date}

CLINICAL INDICATION: {scenario['histology']} of the {scenario['site'].lower()}. {event_context}.

COMPARISON: {comparison}

TECHNIQUE: {"Multidetector CT performed from skull base to iliac crest following administration of 100 mL Omnipaque 350 IV contrast." if "CT" in img_type else "MRI performed with and without IV gadolinium contrast, multiplanar multisequence technique." if "MRI" in img_type else "Whole body bone scintigraphy performed following IV injection of 25 mCi Tc-99m MDP." if "Bone" in img_type else "PET/CT performed following IV injection of 12.5 mCi F-18 FDG. Blood glucose at time of injection: 95 mg/dL."}

FINDINGS:
{findings_text}

IMPRESSION:
{chr(10).join(impression_items)}

Electronically signed by: {pick(rng, ['David Kim, MD', 'Jennifer Walsh, MD', 'Robert Chang, MD', 'Sophia Martinez, MD'])}
Department of Radiology"""



def gen_clinical_note(patient_name, patient_id, scenario, note_date, event_context,
                      is_consult, age, sex, labs_summary, imaging_summary, rng):
    """Generate a detailed clinical note."""
    dept = pick(rng, scenario["departments"][:2])
    note_type = "INITIAL CONSULTATION" if is_consult else "FOLLOW-UP NOTE"

    # HPI
    if is_consult:
        hpi = (
            f"Mr./Ms. {patient_name.split()[-1]} is a {age}-year-old {sex.lower()} "
            f"who presents for initial evaluation of newly diagnosed {scenario['histology'].lower()} "
            f"of the {scenario['site'].lower()}, {scenario['stage']}. "
            f"{pick(rng, ['Patient was referred by primary care physician after abnormal imaging.', 'Patient presented with symptoms prompting workup.', 'Diagnosis made following evaluation of progressive symptoms.'])} "
            f"{scenario['blurb']}. "
            f"Pathology confirmed {scenario['histology'].lower()}. "
            f"Molecular testing {'is pending' if rng.random() > 0.5 else 'has been sent'}. "
            f"Patient reports {pick(rng, ['fatigue and unintentional 10-lb weight loss over 3 months', 'progressive dyspnea and cough x 6 weeks', 'abdominal discomfort and early satiety', 'incidental finding on routine screening', 'palpable mass noted by patient'])}."
        )
    else:
        hpi = (
            f"Mr./Ms. {patient_name.split()[-1]} is a {age}-year-old {sex.lower()} with "
            f"{scenario['stage']} {scenario['histology'].lower()} of the {scenario['site'].lower()} "
            f"who presents for {event_context.lower()}. "
            f"{pick(rng, ['Patient reports feeling well overall.', 'Patient reports mild fatigue but otherwise doing well.', 'Patient has some concerns about side effects.', 'Patient is tolerating treatment reasonably well.'])} "
            f"{pick(rng, ['Appetite has improved.', 'Appetite is decreased but maintaining weight.', 'Weight is stable.', 'Reports mild nausea but eating adequately.'])}"
        )

    # PMH, SH, FH, Meds, Allergies (only for consult)
    consult_sections = ""
    if is_consult:
        n_comorbid = rng.integers(1, 4)
        comorbids = pick_n(rng, COMORBIDITIES, n_comorbid)
        allergy = pick(rng, ALLERGIES_POOL)
        meds = []
        for c in comorbids:
            if "hypertension" in c:
                meds.append("Lisinopril 10 mg daily")
            elif "diabetes" in c:
                meds.append("Metformin 1000 mg BID")
            elif "hyperlipidemia" in c:
                meds.append("Atorvastatin 40 mg daily")
            elif "GERD" in c.lower() or "reflux" in c.lower():
                meds.append("Omeprazole 20 mg daily")
            elif "hypothyroidism" in c:
                meds.append("Levothyroxine 75 mcg daily")
            elif "atrial" in c:
                meds.append("Apixaban 5 mg BID")
        meds_str = ", ".join(meds) if meds else "None"
        fhx_cancer = pick(rng, [
            "Mother with breast cancer at age 62.",
            "Father with colon cancer at age 70.",
            "No family history of cancer.",
            "Sister with ovarian cancer at age 55.",
            "Father with prostate cancer at age 68. Paternal uncle with lung cancer.",
            "No significant family history.",
        ])
        consult_sections = f"""
PAST MEDICAL HISTORY:
{chr(10).join(f'- {c}' for c in comorbids)}

SURGICAL HISTORY:
- {pick(rng, ['Appendectomy (age 25)', 'Cholecystectomy (age 50)', 'No prior surgeries', 'Right knee arthroscopy (age 45)', 'Cesarean section x 2 (if applicable)'])}

SOCIAL HISTORY:
- {pick(rng, SMOKING_STATUS)}
- Alcohol: {pick(rng, ['Social drinker (2-3 drinks/week)', 'Rare alcohol use', 'No alcohol use', 'Former heavy drinker, quit 5 years ago'])}
- Occupation: {pick(rng, ['Retired teacher', 'Accountant', 'Construction worker (retired)', 'Office manager', 'Nurse (retired)', 'Engineer'])}
- Lives with {pick(rng, ['spouse', 'spouse and adult children', 'alone', 'partner'])}

FAMILY HISTORY:
- {fhx_cancer}

ALLERGIES: {allergy}

MEDICATIONS:
{chr(10).join(f'- {m}' for m in meds) if meds else '- None'}
"""

    # ROS
    n_ros_pos = rng.integers(2, 5)
    ros_pos = pick_n(rng, ROS_POSITIVES, n_ros_pos)
    ros_text = "Positive for: " + ", ".join(ros_pos) + ". Remainder of 14-point ROS reviewed and negative."

    # PE
    vitals = (
        f"BP {rng.integers(110, 150)}/{rng.integers(65, 90)}, "
        f"HR {rng.integers(65, 95)}, "
        f"RR {rng.integers(14, 20)}, "
        f"Temp {round(rng.uniform(97.2, 98.8), 1)}F, "
        f"SpO2 {rng.integers(95, 100)}% on RA, "
        f"Wt {round(rng.uniform(55, 100), 1)} kg"
    )
    pe_text = f"""Vitals: {vitals}
General: {pick(rng, ['Alert, oriented, well-appearing, in no acute distress.', 'Comfortable, thin-appearing, no acute distress.', 'Well-nourished, alert, in no distress.'])}
HEENT: {pick(rng, ['NCAT, EOMI, PERRL. Oral mucosa moist without lesions.', 'Normocephalic, atraumatic. Mucous membranes moist.', 'No scleral icterus. Oropharynx clear.'])}
Neck: {pick(rng, ['Supple, no JVD, no cervical lymphadenopathy.', 'No thyromegaly. No lymphadenopathy.'])}
Lungs: {pick(rng, ['Clear to auscultation bilaterally.', 'Diminished breath sounds at right base. No wheezes.', 'Clear bilaterally. No rales or rhonchi.'])}
CV: {pick(rng, ['Regular rate and rhythm, no murmurs.', 'RRR, S1/S2 normal. No murmurs, gallops, or rubs.'])}
Abdomen: {pick(rng, ['Soft, non-tender, non-distended. No hepatosplenomegaly.', 'Soft, mildly tender in RUQ. No rebound. Normoactive bowel sounds.', 'Soft, non-distended. Well-healed midline surgical scar.'])}
Extremities: {pick(rng, ['No edema. No cyanosis or clubbing.', 'Trace bilateral lower extremity edema. Warm and well-perfused.', 'No peripheral edema. Good pulses bilaterally.'])}
Neuro: {pick(rng, ['A&O x3, CN II-XII intact, no focal deficits.', 'Alert and oriented. No focal neurological deficits.'])}"""

    # Assessment and Plan
    assessment = (
        f"{age}-year-old {sex.lower()} with {scenario['stage']} {scenario['histology'].lower()} "
        f"of the {scenario['site'].lower()}. {event_context}."
    )
    plan_items = []
    if is_consult:
        plan_items = [
            f"1. {scenario['histology']} of the {scenario['site'].lower()}, Stage {scenario['stage']}",
            "   - Reviewed pathology and imaging with patient and family",
            f"   - Recommend {scenario['treatments'][0][2]}",
            "   - Will discuss at multidisciplinary tumor board",
            "   - Molecular profiling results pending",
            f"2. Supportive care",
            "   - Nutrition consultation placed",
            "   - Social work referral for psychosocial support",
            f"   - {pick(rng, ['Port placement scheduled', 'PICC line to be placed prior to treatment', 'Peripheral access adequate'])}",
            "3. Follow-up in 1-2 weeks to initiate treatment",
        ]
    else:
        plan_items = [
            f"1. {scenario['histology']} - {event_context}",
            f"   - {pick(rng, ['Continue current treatment regimen', 'Proceed with next cycle as planned', 'Restaging imaging to be scheduled', 'Treatment well tolerated, continue'])}",
            f"   - {pick(rng, ['Labs today show adequate counts for treatment', 'Will check labs prior to next cycle', 'Tumor markers trending favorably', 'Monitoring for treatment-related toxicity'])}",
            f"2. Symptom management",
            f"   - {pick(rng, ['Continue antiemetic regimen', 'Fatigue management discussed', 'Pain well controlled on current regimen', 'Neuropathy being monitored'])}",
            f"3. Follow-up in {pick(rng, ['2 weeks', '3 weeks', '4 weeks', '6 weeks'])}",
        ]

    return f"""{note_type} - {dept}

Patient: {patient_name}
MRN: {patient_id}
Date: {note_date}
Provider: {pick(rng, ['Dr. Amanda Foster', 'Dr. Richard Okafor', 'Dr. Priya Sharma', 'Dr. Carlos Mendez', 'Dr. Helen Park'])}

CHIEF COMPLAINT: {event_context}

HISTORY OF PRESENT ILLNESS:
{hpi}
{consult_sections}
REVIEW OF SYSTEMS:
{ros_text}

PHYSICAL EXAMINATION:
{pe_text}

LABORATORY RESULTS:
{labs_summary if labs_summary else 'See separate lab report.'}

IMAGING:
{imaging_summary if imaging_summary else 'See separate imaging report.'}

ASSESSMENT AND PLAN:
{assessment}

{chr(10).join(plan_items)}

Electronically signed by: {pick(rng, ['Amanda Foster, MD', 'Richard Okafor, MD', 'Priya Sharma, MD', 'Carlos Mendez, MD', 'Helen Park, MD'])}
{dept}"""


def gen_ngs_report(patient_name, patient_id, scenario, report_date, rng):
    """Generate an NGS genomic report."""
    ngs = scenario["ngs"]
    tmb = round(rng.uniform(*ngs["tmb_range"]), 1)
    panel_name = pick(rng, ["FoundationOne CDx", "Tempus xT", "MSK-IMPACT", "Guardant360 CDx"])
    n_genes = pick(rng, [324, 468, 523, 648])

    actionable_lines = []
    for gene, variant, var_type, exon in ngs["actionable"]:
        exon_str = f" ({exon})" if exon else ""
        actionable_lines.append(f"  {gene} {variant} - {var_type}{exon_str} [Clinically Significant]")

    comut_lines = []
    n_comut = min(len(ngs["comutations"]), rng.integers(1, len(ngs["comutations"]) + 1))
    chosen_comuts = pick_n(rng, ngs["comutations"], n_comut)
    for gene, variant, var_type, exon in chosen_comuts:
        exon_str = f" ({exon})" if exon else ""
        comut_lines.append(f"  {gene} {variant} - {var_type}{exon_str}")

    vus_lines = []
    for gene, variant, classification in ngs["vus"]:
        vus_lines.append(f"  {gene} {variant} - {classification}")

    return f"""NEXT GENERATION SEQUENCING REPORT

Patient: {patient_name}
MRN: {patient_id}
Date of Report: {report_date}
Specimen: {scenario['site']} ({pick(rng, ['Biopsy', 'Resection', 'Core needle biopsy', 'FNA cell block'])})
Diagnosis: {scenario['histology']}
Panel: {panel_name} ({n_genes} genes)

RESULTS SUMMARY:
Tumor Mutational Burden (TMB): {tmb} mutations/Mb {'(Low)' if tmb < 10 else '(Intermediate)' if tmb < 20 else '(High)'}
Microsatellite Status: {ngs['msi']}

CLINICALLY SIGNIFICANT GENOMIC ALTERATIONS:
{chr(10).join(actionable_lines)}

ADDITIONAL PATHOGENIC ALTERATIONS:
{chr(10).join(comut_lines) if comut_lines else '  None identified'}

VARIANTS OF UNCERTAIN SIGNIFICANCE:
{chr(10).join(vus_lines) if vus_lines else '  None identified'}

COPY NUMBER ALTERATIONS:
  {'CDKN2A homozygous deletion' if any('CDKN2A' in str(c) and 'deletion' in str(c).lower() for c in ngs['comutations']) else 'No significant copy number alterations detected'}

FUSIONS:
  {'No pathogenic fusions detected.' if scenario['label'] != 'nsclc_egfr' else 'No ALK, ROS1, RET, or NTRK fusions detected.'}

THERAPY ASSOCIATIONS:
{_therapy_associations(scenario, ngs)}

Note: This test was performed using hybrid capture-based next generation sequencing.
Sequencing depth: mean {rng.integers(400, 800)}x coverage.
Tumor content: {rng.integers(20, 80)}%.

Electronically signed by: {pick(rng, ['Katherine Liu, MD, PhD', 'Andrew Patel, MD', 'Maria Santos, MD, PhD'])}
Molecular Pathology Laboratory"""


def _therapy_associations(scenario, ngs):
    """Generate therapy association text for NGS report."""
    associations = {
        "nsclc_egfr": "  - EGFR L858R: FDA-approved targeted therapies include osimertinib (preferred), erlotinib, afatinib, gefitinib.\n  - PD-L1 expression should be assessed for immunotherapy eligibility.",
        "breast_her2": "  - ERBB2 amplification: FDA-approved HER2-directed therapies include trastuzumab, pertuzumab, T-DXd, tucatinib.\n  - PIK3CA H1047R: Alpelisib may be considered in HR+/HER2- setting.",
        "colon": "  - KRAS wild-type: Patient eligible for anti-EGFR therapy (cetuximab, panitumumab) if disease progresses.\n  - MSS: Unlikely to benefit from single-agent immune checkpoint inhibitor.",
        "melanoma_braf": "  - BRAF V600E: FDA-approved BRAF/MEK inhibitors include dabrafenib/trametinib, encorafenib/binimetinib, vemurafenib/cobimetinib.",
        "ovarian_hgsoc": "  - BRCA1 pathogenic variant: FDA-approved PARP inhibitors include olaparib, niraparib, rucaparib.\n  - Platinum sensitivity expected.",
        "prostate_crpc": "  - BRCA2 pathogenic variant: FDA-approved PARP inhibitor olaparib indicated for HRR-mutated mCRPC.\n  - Consider platinum-based chemotherapy.",
        "pancreatic": "  - KRAS G12D: Investigational KRAS G12D inhibitors in clinical trials.\n  - BRCA/PALB2 VUS noted - genetic counseling recommended.",
        "bladder": "  - FGFR3 S249C: FDA-approved erdafitinib for FGFR-altered advanced urothelial carcinoma.\n  - Elevated TMB may support immunotherapy benefit.",
        "renal_cc": "  - VHL mutation: Consistent with clear cell histology. HIF-pathway targeted therapies (TKIs) and immunotherapy combinations recommended.\n  - BAP1 loss: Associated with more aggressive biology.",
        "head_neck_scc": "  - HPV-positive disease: Generally favorable prognosis. De-escalation trials may be appropriate.\n  - PIK3CA mutation: Alpelisib under investigation in HNSCC.",
    }
    return associations.get(scenario["label"], "  No specific therapy associations identified.")



# ---------------------------------------------------------------------------
# Lab generation
# ---------------------------------------------------------------------------

def generate_labs(patient_id, scenario, events, event_dates, rng):
    """Generate lab results for a patient based on their treatment timeline."""
    labs = []
    scenario_idx = scenario["index"]
    scenario_label = scenario["label"]

    # Baseline lab values
    baseline = {
        "WBC": round(rng.uniform(5.0, 9.0), 1),
        "Hemoglobin": round(rng.uniform(12.5, 15.5), 1),
        "Platelets": round(rng.uniform(180, 350), 0),
        "Creatinine": round(rng.uniform(0.7, 1.1), 2),
        "BUN": round(rng.uniform(10, 18), 0),
        "ALT": round(rng.uniform(15, 40), 0),
        "AST": round(rng.uniform(15, 35), 0),
        "Albumin": round(rng.uniform(3.8, 4.5), 1),
        "Total Bilirubin": round(rng.uniform(0.3, 0.9), 1),
    }
    current = dict(baseline)

    # Track treatment phase for lab modifications
    on_chemo = False
    on_immunotherapy = False
    chemo_cycle = 0
    tumor_marker_baseline = {}
    for marker in scenario["tumor_markers"]:
        ref = LAB_REFERENCE[marker]
        # Start elevated for cancer patients
        tumor_marker_baseline[marker] = round(rng.uniform(ref["high"] * 1.5, ref["high"] * 5), 1)

    tumor_marker_current = dict(tumor_marker_baseline)
    responding = rng.random() > 0.3  # 70% chance of response

    for i, (event, evt_date) in enumerate(zip(events, event_dates)):
        etype = event["type"]

        # Determine if this event generates labs
        generates_labs = etype in ("systemic", "surgery", "clinical_note", "radiation")
        if etype == "imaging_report" and rng.random() > 0.6:
            generates_labs = True  # Some imaging visits also get labs
        if not generates_labs:
            continue

        # Modify lab values based on treatment phase
        if etype == "systemic":
            drug_text = event["text"].lower()
            if any(chemo in drug_text for chemo in ["carboplatin", "cisplatin", "docetaxel", "paclitaxel",
                                                      "folfox", "folfirinox", "gemcitabine", "5-fu",
                                                      "capecitabine", "irinotecan", "cabazitaxel"]):
                on_chemo = True
                chemo_cycle += 1
                # Myelosuppression
                current["WBC"] = clamp(round(baseline["WBC"] * rng.uniform(0.3, 0.7), 1), 0.8, 15.0)
                current["Hemoglobin"] = clamp(round(baseline["Hemoglobin"] * rng.uniform(0.7, 0.9), 1), 6.5, 18.0)
                current["Platelets"] = clamp(round(baseline["Platelets"] * rng.uniform(0.4, 0.8), 0), 30, 500)
            elif any(io in drug_text for io in ["nivolumab", "pembrolizumab", "ipilimumab", "durvalumab", "atezolizumab"]):
                on_immunotherapy = True
                # Possible LFT elevation
                if rng.random() > 0.7:
                    current["ALT"] = round(baseline["ALT"] * rng.uniform(1.5, 3.0), 0)
                    current["AST"] = round(baseline["AST"] * rng.uniform(1.5, 2.5), 0)
            else:
                # Targeted therapy - generally well tolerated
                on_chemo = False

            # Tumor marker changes
            if responding:
                for marker in tumor_marker_current:
                    tumor_marker_current[marker] = clamp(
                        round(tumor_marker_current[marker] * rng.uniform(0.5, 0.85), 1),
                        LAB_REFERENCE[marker]["low"],
                        LAB_REFERENCE[marker]["high"] * 20
                    )
            else:
                for marker in tumor_marker_current:
                    tumor_marker_current[marker] = clamp(
                        round(tumor_marker_current[marker] * rng.uniform(1.0, 1.3), 1),
                        LAB_REFERENCE[marker]["low"],
                        LAB_REFERENCE[marker]["high"] * 20
                    )

        elif etype == "clinical_note":
            # Recovery between cycles
            if on_chemo:
                current["WBC"] = clamp(round(current["WBC"] + rng.uniform(1.0, 3.0), 1), 1.0, 15.0)
                current["Hemoglobin"] = clamp(round(current["Hemoglobin"] + rng.uniform(0.3, 0.8), 1), 7.0, 17.0)
                current["Platelets"] = clamp(round(current["Platelets"] + rng.uniform(20, 80), 0), 50, 450)
            if on_immunotherapy and current["ALT"] > baseline["ALT"]:
                current["ALT"] = clamp(round(current["ALT"] * rng.uniform(0.6, 0.9), 0), 10, 200)
                current["AST"] = clamp(round(current["AST"] * rng.uniform(0.6, 0.9), 0), 10, 150)

        # Generate lab rows
        # CBC
        for test_name in ["WBC", "Hemoglobin", "Platelets"]:
            val = round(current[test_name] + rng.normal(0, current[test_name] * 0.05), 1)
            val = clamp(val, 0.5 if test_name == "WBC" else 5.0 if test_name == "Hemoglobin" else 20, 20 if test_name == "WBC" else 19.0 if test_name == "Hemoglobin" else 600)
            ref = LAB_REFERENCE[test_name]
            labs.append({
                "patient_id": patient_id,
                "date": evt_date,
                "test_name": test_name,
                "value": str(round(val, 1)),
                "unit": ref["unit"],
                "reference_range": ref["range"],
                "abnormal_flag": abnormal_flag(val, ref),
                "scenario_index": scenario_idx,
                "scenario_label": scenario_label,
            })

        # CMP (for most visits)
        if etype in ("systemic", "surgery", "clinical_note") or rng.random() > 0.5:
            for test_name in ["Creatinine", "BUN", "ALT", "AST", "Albumin"]:
                val = round(current[test_name] + rng.normal(0, current[test_name] * 0.08), 1 if test_name != "Creatinine" else 2)
                ref = LAB_REFERENCE[test_name]
                val = clamp(val, ref["low"] * 0.3, ref["high"] * 5)
                labs.append({
                    "patient_id": patient_id,
                    "date": evt_date,
                    "test_name": test_name,
                    "value": str(round(val, 1 if test_name != "Creatinine" else 2)),
                    "unit": ref["unit"],
                    "reference_range": ref["range"],
                    "abnormal_flag": abnormal_flag(val, ref),
                    "scenario_index": scenario_idx,
                    "scenario_label": scenario_label,
                })

        # Tumor markers (periodic)
        if scenario["tumor_markers"] and (etype in ("systemic", "clinical_note") or rng.random() > 0.6):
            for marker in scenario["tumor_markers"]:
                val = round(tumor_marker_current[marker] + rng.normal(0, tumor_marker_current[marker] * 0.1), 1)
                val = clamp(val, 0.1, LAB_REFERENCE[marker]["high"] * 30)
                ref = LAB_REFERENCE[marker]
                labs.append({
                    "patient_id": patient_id,
                    "date": evt_date,
                    "test_name": marker,
                    "value": str(round(val, 1)),
                    "unit": ref["unit"],
                    "reference_range": ref["range"],
                    "abnormal_flag": abnormal_flag(val, ref),
                    "scenario_index": scenario_idx,
                    "scenario_label": scenario_label,
                })

        # PT/INR for pre-surgical visits
        if etype == "surgery":
            val = round(rng.uniform(0.9, 1.15), 1)
            ref = LAB_REFERENCE["PT/INR"]
            labs.append({
                "patient_id": patient_id,
                "date": evt_date,
                "test_name": "PT/INR",
                "value": str(val),
                "unit": ref["unit"],
                "reference_range": ref["range"],
                "abnormal_flag": abnormal_flag(val, ref),
                "scenario_index": scenario_idx,
                "scenario_label": scenario_label,
            })

    return labs


# ---------------------------------------------------------------------------
# Encounter generation
# ---------------------------------------------------------------------------

def generate_encounters(patient_id, scenario, events, event_dates):
    """Generate encounter rows from events."""
    encounters = []
    encounter_types = {"systemic", "surgery", "radiation", "clinical_note",
                       "imaging_report", "pathology_report", "ngs_report", "adverse_event"}

    dept_map = {
        "imaging_report": "Radiology",
        "pathology_report": "Pathology",
        "ngs_report": "Pathology",
        "adverse_event": "Emergency",
    }
    visit_map = {
        "systemic": "Infusion",
        "surgery": "Procedure",
        "radiation": "Procedure",
        "imaging_report": "Imaging",
        "pathology_report": "Procedure",
        "ngs_report": "Procedure",
        "adverse_event": "ED",
    }

    is_first_visit = True
    for event, evt_date in zip(events, event_dates):
        etype = event["type"]
        if etype not in encounter_types:
            continue

        if etype == "clinical_note":
            dept = scenario["departments"][0]  # primary oncology dept
            vtype = "New Patient" if is_first_visit else "Follow-up"
            is_first_visit = False
        elif etype == "systemic":
            dept = "Medical Oncology"
            vtype = visit_map[etype]
        elif etype == "surgery":
            dept = next((d for d in scenario["departments"] if "Surgery" in d or "Gynecologic" in d), "Surgery")
            vtype = visit_map[etype]
        elif etype == "radiation":
            dept = "Radiation Oncology"
            vtype = visit_map[etype]
        elif etype == "adverse_event":
            dept = "Emergency" if "grade 3" in event["text"].lower() or "grade 4" in event["text"].lower() else "Medical Oncology"
            vtype = "ED" if dept == "Emergency" else "Follow-up"
        else:
            dept = dept_map.get(etype, scenario["departments"][0])
            vtype = visit_map.get(etype, "Follow-up")

        encounters.append({
            "patient_id": patient_id,
            "date": evt_date,
            "diagnosis_code": scenario["icd10"],
            "department": dept,
            "visit_type": vtype,
            "scenario_index": scenario["index"],
            "scenario_label": scenario["label"],
        })

    return encounters



# ---------------------------------------------------------------------------
# Patient timeline generation
# ---------------------------------------------------------------------------

def generate_patient(scenario, patient_num, rng):
    """Generate a complete patient record."""
    patient_id = make_patient_id()

    # Demographics
    sex = "Male" if rng.random() < scenario["sex_weights"][0] else "Female"
    age = int(rng.integers(*scenario["age_range"]))
    if sex == "Male":
        first_name = pick(rng, MALE_FIRST_NAMES)
    else:
        first_name = pick(rng, FEMALE_FIRST_NAMES)
    last_name = pick(rng, LAST_NAMES)
    patient_name = f"{first_name} {last_name}"

    # Diagnosis date
    base_date = date(2022, 1, 1) + timedelta(days=int(rng.integers(0, 730)))

    # TNM staging
    tnm_t = pick(rng, scenario["tnm"]["T"])
    tnm_n = pick(rng, scenario["tnm"]["N"])
    tnm_m = pick(rng, scenario["tnm"]["M"])

    # Build event timeline as (day_offset, event_type, event_text, event_context)
    timeline = []

    # Phase 1: Diagnosis (days 0-21)
    timeline.append((0, "demographics", gen_demographics_text(patient_name, age, sex, rng), ""))
    timeline.append((0, "diagnosis", gen_diagnosis_text(scenario, (tnm_t, tnm_n, tnm_m), rng), ""))
    timeline.append((rand_date_offset(rng, 3, 7), "pathology_report", "", "initial biopsy"))
    timeline.append((rand_date_offset(rng, 1, 5), "imaging_report", "", "baseline staging"))
    timeline.append((rand_date_offset(rng, 14, 25), "ngs_report", "", "molecular profiling"))
    timeline.append((rand_date_offset(rng, 7, 14), "clinical_note", "", "initial oncology consultation"))

    # Phase 2: Treatment (days ~21-300)
    day = 28
    treatments = list(scenario["treatments"])

    # Decide whether to use some alternative treatments
    if rng.random() > 0.6 and scenario["alt_treatments"]:
        # Replace last treatment with an alternative
        alt = pick(rng, scenario["alt_treatments"])
        treatments[-1] = alt

    for tx_idx, tx in enumerate(treatments):
        tx_type, tx_desc, tx_intent = tx

        if tx_type == "systemic":
            # Determine number of cycles
            if "q3w" in tx_desc and "x" in tx_desc:
                try:
                    n_cycles = int(tx_desc.split("x")[1].strip().split()[0])
                except (IndexError, ValueError):
                    n_cycles = 4
                interval = 21
            elif "q2w" in tx_desc and "x" in tx_desc:
                try:
                    n_cycles = int(tx_desc.split("x")[1].strip().split()[0])
                except (IndexError, ValueError):
                    n_cycles = 6
                interval = 14
            elif "q4w" in tx_desc and "x" in tx_desc:
                try:
                    n_cycles = int(tx_desc.split("x")[1].strip().split()[0])
                except (IndexError, ValueError):
                    n_cycles = 4
                interval = 28
            elif "daily" in tx_desc.lower() or "bid" in tx_desc.lower():
                # Oral therapy - just a start event and periodic follow-ups
                timeline.append((day, "systemic", gen_systemic_text(tx), tx_intent))
                timeline.append((day + 28, "clinical_note", "", f"follow-up on {tx_intent}"))
                timeline.append((day + 56, "clinical_note", "", f"follow-up on {tx_intent}"))
                if rng.random() > 0.5:
                    timeline.append((day + 84, "imaging_report", "", f"restaging on {tx_intent}"))
                day += 90
                continue
            else:
                n_cycles = rng.integers(3, 7)
                interval = 21

            for cycle in range(1, n_cycles + 1):
                cycle_day = day + (cycle - 1) * interval
                timeline.append((cycle_day, "systemic", gen_systemic_text(tx, cycle), f"cycle {cycle} of {tx_intent}"))

                # Adverse event chance
                if rng.random() > 0.55:
                    ae = pick(rng, scenario["adverse_events"])
                    ae_day = cycle_day + rand_date_offset(rng, 3, 12)
                    timeline.append((ae_day, "adverse_event", gen_adverse_event_text(ae[0], ae[1], rng), ""))

                # Mid-treatment clinical note
                if cycle % 2 == 0:
                    timeline.append((cycle_day + rand_date_offset(rng, 1, 3), "clinical_note", "", f"cycle {cycle} assessment"))

            # Restaging imaging after treatment block
            restage_day = day + n_cycles * interval + rand_date_offset(rng, 7, 14)
            timeline.append((restage_day, "imaging_report", "", f"restaging after {tx_intent}"))
            timeline.append((restage_day + rand_date_offset(rng, 1, 5), "clinical_note", "", f"results review after {tx_intent}"))
            day = restage_day + 14

        elif tx_type == "surgery":
            timeline.append((day, "surgery", gen_surgery_text(tx, rng), tx_intent))
            timeline.append((day + rand_date_offset(rng, 5, 10), "pathology_report", "", "surgical pathology"))
            timeline.append((day + rand_date_offset(rng, 14, 21), "clinical_note", "", "postoperative follow-up"))
            day += 42

        elif tx_type == "radiation":
            timeline.append((day, "radiation", gen_radiation_text(tx), tx_intent))
            # Radiation is typically daily for weeks
            if "35 fractions" in tx_desc:
                day += 49  # 7 weeks
            elif "30 fractions" in tx_desc:
                day += 42
            elif "10 fractions" in tx_desc:
                day += 14
            elif "5 fractions" in tx_desc:
                day += 7
            else:
                day += 28
            timeline.append((day, "clinical_note", "", "post-radiation assessment"))
            day += 14

    # Phase 3: Follow-up / Surveillance (up to ~day 900)
    surveillance_start = day
    n_followups = rng.integers(3, 7)
    for fu in range(n_followups):
        fu_day = surveillance_start + (fu + 1) * rand_date_offset(rng, 60, 100)
        timeline.append((fu_day, "clinical_note", "", "surveillance follow-up"))
        if fu % 2 == 0:
            timeline.append((fu_day + rand_date_offset(rng, -5, 5), "imaging_report", "", "surveillance imaging"))

    # Sort timeline by day offset
    timeline.sort(key=lambda x: x[0])

    # Convert to events with dates
    events = []
    event_dates = []
    documents = []
    doc_events_generated = {"pathology_report": False, "ngs_report": False}

    for day_offset, etype, text, context in timeline:
        evt_date = format_date(base_date, day_offset)

        # Generate text for events that need it
        if etype == "pathology_report":
            if not text:
                text = f"Pathology specimen received for {context}."
            events.append({"type": etype, "text": text})
            event_dates.append(evt_date)
            # Generate document
            doc_text = gen_pathology_report(patient_name, patient_id, scenario, evt_date, rng)
            documents.append({
                "event_index": len(events) - 1,
                "event_type": etype,
                "text": doc_text,
            })

        elif etype == "imaging_report":
            img_type = pick(rng, scenario["imaging_types"])
            if not text:
                text = f"{img_type} performed for {context}."
            events.append({"type": etype, "text": text})
            event_dates.append(evt_date)
            doc_text = gen_imaging_report(patient_name, patient_id, scenario, evt_date, img_type, context, rng)
            documents.append({
                "event_index": len(events) - 1,
                "event_type": etype,
                "text": doc_text,
            })

        elif etype == "clinical_note":
            if not text:
                text = f"Clinical visit for {context}."
            events.append({"type": etype, "text": text})
            event_dates.append(evt_date)
            is_consult = context and "consult" in context.lower()
            # Simple labs summary for the note
            labs_summary = f"WBC {round(rng.uniform(3.0, 10.0),1)}, Hgb {round(rng.uniform(9.0, 15.0),1)}, Plt {int(rng.integers(100, 350))}, Cr {round(rng.uniform(0.7, 1.2),2)}"
            imaging_summary = f"Most recent imaging reviewed." if not is_consult else ""
            doc_text = gen_clinical_note(patient_name, patient_id, scenario, evt_date, context,
                                         is_consult, age, sex, labs_summary, imaging_summary, rng)
            documents.append({
                "event_index": len(events) - 1,
                "event_type": etype,
                "text": doc_text,
            })

        elif etype == "ngs_report":
            if not text:
                text = f"NGS report received for {context}."
            events.append({"type": etype, "text": text})
            event_dates.append(evt_date)
            doc_text = gen_ngs_report(patient_name, patient_id, scenario, evt_date, rng)
            documents.append({
                "event_index": len(events) - 1,
                "event_type": etype,
                "text": doc_text,
            })

        else:
            if not text:
                text = f"{etype} event."
            events.append({"type": etype, "text": text})
            event_dates.append(evt_date)

    # Generate tables
    encounter_rows = generate_encounters(patient_id, scenario, events, event_dates)
    lab_rows = generate_labs(patient_id, scenario, events, event_dates, rng)

    return {
        "patient_id": patient_id,
        "events": events,
        "documents": documents,
        "tables": {
            "encounters": encounter_rows,
            "labs": lab_rows,
        },
        "scenario_index": scenario["index"],
        "scenario_blurb": scenario["blurb"],
        "scenario_label": scenario["label"],
    }


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------

def main():
    patients_dir = OUTPUT_DIR / "patients"
    tables_dir = OUTPUT_DIR / "tables"
    patients_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    all_documents = []
    all_encounters = []
    all_labs = []
    total_events = 0
    scenario_stats = {}

    print(f"Generating synthetic data for {len(SCENARIOS)} scenarios x 5 patients = {len(SCENARIOS)*5} patients")
    print(f"Output directory: {OUTPUT_DIR}")

    for scenario in SCENARIOS:
        scenario_idx = scenario["index"]
        scenario_events = 0
        scenario_patients = 0

        for patient_num in range(5):
            rng = np.random.default_rng(seed=scenario_idx * 100 + patient_num + 42)
            patient = generate_patient(scenario, patient_num, rng)

            # Write per-patient JSON
            patient_file = patients_dir / f"{patient['patient_id']}.json"
            with open(patient_file, "w") as f:
                json.dump(patient, f, indent=2)

            # Collect for aggregated outputs
            for doc in patient["documents"]:
                all_documents.append({
                    "patient_id": patient["patient_id"],
                    "scenario_index": scenario_idx,
                    "scenario_label": scenario["label"],
                    **doc,
                })

            all_encounters.extend(patient["tables"]["encounters"])
            all_labs.extend(patient["tables"]["labs"])
            total_events += len(patient["events"])
            scenario_events += len(patient["events"])
            scenario_patients += 1

            print(f"  [{scenario['label']}] Patient {patient_num+1}/5: {patient['patient_id']} "
                  f"({len(patient['events'])} events, {len(patient['documents'])} docs)")

        scenario_stats[str(scenario_idx)] = {
            "label": scenario["label"],
            "blurb": scenario["blurb"],
            "patients": scenario_patients,
            "events": scenario_events,
        }

    # Write all_documents.json
    docs_file = OUTPUT_DIR / "all_documents.json"
    with open(docs_file, "w") as f:
        json.dump(all_documents, f, indent=2)
    print(f"\nWrote {len(all_documents)} documents to {docs_file}")

    # Write encounters CSV
    enc_file = tables_dir / "encounters.csv"
    enc_df = pd.DataFrame(all_encounters)
    enc_cols = ["patient_id", "date", "diagnosis_code", "department", "visit_type",
                "scenario_index", "scenario_label"]
    enc_df = enc_df[enc_cols]
    enc_df.to_csv(enc_file, index=False)
    print(f"Wrote {len(enc_df)} encounter rows to {enc_file}")

    # Write labs CSV
    labs_file = tables_dir / "labs.csv"
    labs_df = pd.DataFrame(all_labs)
    labs_cols = ["patient_id", "date", "test_name", "value", "unit", "reference_range",
                 "abnormal_flag", "scenario_index", "scenario_label"]
    labs_df = labs_df[labs_cols]
    labs_df.to_csv(labs_file, index=False)
    print(f"Wrote {len(labs_df)} lab rows to {labs_file}")

    # Write summary.json
    patient_count = len(SCENARIOS) * 5
    summary = {
        "patient_count": patient_count,
        "total_events": total_events,
        "avg_events_per_patient": round(total_events / patient_count, 1),
        "document_count": len(all_documents),
        "table_row_counts": {
            "encounters": len(all_encounters),
            "labs": len(all_labs),
        },
        "output_files": {
            "documents": str(docs_file),
            "tables": {
                "encounters": str(enc_file),
                "labs": str(labs_file),
            },
            "summary": str(OUTPUT_DIR / "summary.json"),
        },
        "scenarios": scenario_stats,
    }
    summary_file = OUTPUT_DIR / "summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary written to {summary_file}")
    print(f"Total: {patient_count} patients, {total_events} events, "
          f"{len(all_documents)} documents, {len(all_encounters)} encounters, {len(all_labs)} labs")


if __name__ == "__main__":
    main()
