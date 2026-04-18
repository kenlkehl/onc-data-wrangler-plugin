"""Drug name perturbation utilities for synthetic clinical notes.

Replaces generic oncology drug names with brand names or common abbreviations
to increase realism of generated clinical text. Ported from matchminer-ai-training.
"""

from __future__ import annotations

import re
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Default drug map: generic -> [brand/abbreviation alternatives]
# Brand pairs sourced from NCI Drug Dictionary.
# ---------------------------------------------------------------------------

DEFAULT_DRUG_MAP: dict[str, list[str]] = {
    # PD-(L)1 & CTLA-4
    "pembrolizumab": ["Keytruda", "pembro"],
    "nivolumab": ["Opdivo", "nivo"],
    "ipilimumab": ["Yervoy", "ipi"],
    "atezolizumab": ["Tecentriq", "atezo"],
    "durvalumab": ["Imfinzi", "durva"],
    "cemiplimab": ["Libtayo", "cemi"],

    # Platinums & taxanes
    "carboplatin": ["Paraplatin", "carbo"],
    "cisplatin": ["Platinol", "cis"],
    "oxaliplatin": ["Eloxatin", "oxali"],
    "paclitaxel": ["Taxol", "pacli", "PTX"],
    "docetaxel": ["Taxotere", "doce"],
    "nab-paclitaxel": ["Abraxane", "nab-pac"],

    # Antimetabolites
    "capecitabine": ["Xeloda", "cape"],
    "fluorouracil": ["5-FU", "Adrucil", "5FU"],
    "5-fluorouracil": ["5-FU", "Adrucil", "5FU"],
    "gemcitabine": ["Gemzar", "gem"],
    "pemetrexed": ["Alimta", "peme", "pem"],
    "methotrexate": ["MTX", "Trexall"],

    # Anthracyclines & others
    "doxorubicin": ["Adriamycin", "doxo"],
    "epirubicin": ["Ellence", "epi"],
    "cyclophosphamide": ["Cytoxan", "CTX", "cyclo"],
    "etoposide": ["VP-16", "eto"],
    "irinotecan": ["Camptosar", "iri"],
    "topotecan": ["Hycamtin", "topo"],

    # HER2 axis
    "trastuzumab": ["Herceptin", "trast"],
    "pertuzumab": ["Perjeta", "pertu"],
    "ado-trastuzumab emtansine": ["Kadcyla", "T-DM1"],
    "trastuzumab emtansine": ["Kadcyla", "T-DM1"],
    "trastuzumab deruxtecan": ["Enhertu", "T-DXd"],
    "tucatinib": ["Tukysa", "tuca"],
    "lapatinib": ["Tykerb", "lapa"],

    # CDK4/6
    "palbociclib": ["Ibrance", "palbo"],
    "ribociclib": ["Kisqali", "ribo"],
    "abemaciclib": ["Verzenio", "abema"],

    # PARP
    "olaparib": ["Lynparza", "ola"],
    "niraparib": ["Zejula", "nira"],
    "rucaparib": ["Rubraca", "ruca"],
    "talazoparib": ["Talzenna", "tala"],

    # VEGF axis
    "bevacizumab": ["Avastin", "bev"],
    "ramucirumab": ["Cyramza", "ramu"],

    # EGFR, ALK, etc.
    "osimertinib": ["Tagrisso", "osi"],
    "erlotinib": ["Tarceva", "erlo"],
    "gefitinib": ["Iressa", "gefi"],
    "afatinib": ["Gilotrif", "afat"],
    "dacomitinib": ["Vizimpro", "daco"],
    "alectinib": ["Alecensa", "alec"],
    "ceritinib": ["Zykadia", "ceri"],
    "crizotinib": ["Xalkori", "crizo"],
    "lorlatinib": ["Lorbrena", "lorla"],

    # BRAF/MEK
    "dabrafenib": ["Tafinlar", "dabra"],
    "trametinib": ["Mekinist", "tram"],
    "vemurafenib": ["Zelboraf", "vem"],
    "encorafenib": ["Braftovi", "enco"],
    "binimetinib": ["Mektovi", "bini"],

    # Multi-TKIs
    "lenvatinib": ["Lenvima", "lenva"],
    "sorafenib": ["Nexavar", "sora"],
    "regorafenib": ["Stivarga", "rego"],
    "pazopanib": ["Votrient", "pazo"],
    "sunitinib": ["Sutent", "suni"],

    # Antibodies (other)
    "rituximab": ["Rituxan", "ritux"],
    "cetuximab": ["Erbitux", "cetux"],
    "panitumumab": ["Vectibix", "pani"],

    # GU agents
    "enzalutamide": ["Xtandi", "enza"],
    "abiraterone": ["Zytiga", "abi"],
    "apalutamide": ["Erleada", "apa"],
    "leuprolide": ["Lupron", "leup"],
    "degarelix": ["Firmagon", "dega"],
    "relugolix": ["Orgovyx", "relu"],

    # mTOR, alkylators, myeloma, etc.
    "everolimus": ["Afinitor", "evero"],
    "sirolimus": ["Rapamune", "siro"],
    "temozolomide": ["Temodar", "TMZ"],
    "bortezomib": ["Velcade", "bortez"],
    "carfilzomib": ["Kyprolis", "carfil"],
    "ixazomib": ["Ninlaro", "ixa"],
    "daratumumab": ["Darzalex", "dara"],
    "obinutuzumab": ["Gazyva", "obinu"],
}


# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

def compile_replacement_patterns(
    drug_map: dict[str, list[str]],
) -> list[tuple[re.Pattern, list[str]]]:
    """Compile word-boundary regex patterns sorted by key length (longest first).

    Sorting by descending key length avoids partial-match issues
    (e.g., "nab-paclitaxel" before "paclitaxel").
    """
    items = sorted(drug_map.items(), key=lambda kv: len(kv[0]), reverse=True)
    compiled = []
    for generic, alts in items:
        pat = re.compile(rf"\b{re.escape(generic)}\b", flags=re.IGNORECASE)
        compiled.append((pat, alts))
    return compiled


def load_drug_map(csv_path: Optional[str]) -> dict[str, list[str]]:
    """Load a custom drug map from CSV, or return the default.

    CSV format: columns ``generic`` and ``alternatives`` (pipe-separated).
    """
    if not csv_path:
        return DEFAULT_DRUG_MAP
    import pandas as pd

    df = pd.read_csv(csv_path)
    out: dict[str, list[str]] = {}
    for _, row in df.iterrows():
        generic = str(row["generic"]).strip()
        alts = [a.strip() for a in str(row["alternatives"]).split("|") if a.strip()]
        if generic and alts:
            out[generic] = alts
    return out


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

def apply_drug_perturbation(
    text: str,
    patterns: list[tuple[re.Pattern, list[str]]],
    rng: np.random.Generator,
) -> str:
    """Replace every occurrence of matched generics with a random alternative."""
    for pat, alts in patterns:
        text = pat.sub(lambda _m: rng.choice(alts), text)
    return text
