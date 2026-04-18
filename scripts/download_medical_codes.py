#!/usr/bin/env python3
"""Download / install full releases of ICD-10-CM, LOINC, and SNOMED CT.

Writes normalized CSVs (``code,description,category``) into
``data/ontologies/medical_codes/<vocab>/full/`` so ``MedicalCodeRegistry``
prefers them over the bundled subset.

Usage
-----
    # ICD-10-CM: public, fetched directly from CMS.
    python scripts/download_medical_codes.py --icd10

    # LOINC: requires a loinc.org account; point at the Loinc.csv from
    # the LoincTableCore.zip you downloaded.
    python scripts/download_medical_codes.py --loinc /path/to/Loinc.csv

    # SNOMED CT: requires a UMLS/IHTSDO affiliate license. Point at the
    # RF2 Snapshot Terminology directory (contains
    # sct2_Description_Snapshot-en_*.txt).
    python scripts/download_medical_codes.py --snomed /path/to/Snapshot/Terminology
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

logger = logging.getLogger("download_medical_codes")

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
MEDICAL_CODES_ROOT = PLUGIN_ROOT / "data" / "ontologies" / "medical_codes"

# ICD-10-CM public source. CMS publishes the FY tabular order file;
# if the URL changes in a future FY, --icd10-url lets users override.
DEFAULT_ICD10_URL = (
    "https://www.cms.gov/files/zip/2025-code-descriptions-tabular-order-updated-02/01/2024.zip"
)


# ---------------------------------------------------------------------------
# ICD-10-CM
# ---------------------------------------------------------------------------

def download_icd10cm(url: str, out_dir: Path) -> Path:
    """Fetch CMS ICD-10-CM zip and write ``icd10cm_codes_full.csv``.

    The CMS release includes ``icd10cm_codes_YYYY.txt``: a simple space-
    delimited file of ``<CODE> <DESCRIPTION>`` lines. We parse those.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading ICD-10-CM from %s", url)
    with urllib.request.urlopen(url) as resp:
        data = resp.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        # Find the plain codes file (not the tabular XML).
        candidates = [
            n for n in zf.namelist()
            if re.match(r".*icd10cm_codes_\d{4}\.txt$", n, re.IGNORECASE)
        ]
        if not candidates:
            raise RuntimeError(
                "Could not find icd10cm_codes_*.txt inside the CMS zip. "
                "Inspect the archive manually and update this script."
            )
        codes_path = candidates[0]
        logger.info("Extracting %s", codes_path)
        with zf.open(codes_path) as fh:
            lines = fh.read().decode("utf-8", errors="replace").splitlines()

    out_csv = out_dir / "icd10cm_codes_full.csv"
    n = 0
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["code", "description", "category"])
        for line in lines:
            line = line.rstrip()
            if not line:
                continue
            # Format: "<CODE><spaces><DESCRIPTION>". Code is a single token.
            m = re.match(r"^([A-Z0-9.]+)\s+(.*)$", line)
            if not m:
                continue
            code, desc = m.group(1), m.group(2)
            # Insert the decimal after the 3rd character if not present,
            # matching the conventional ICD-10-CM form (e.g., C5091 -> C50.91).
            if "." not in code and len(code) > 3:
                code = f"{code[:3]}.{code[3:]}"
            category = _icd10_category(code)
            writer.writerow([code, desc, category])
            n += 1
    logger.info("Wrote %d ICD-10-CM rows to %s", n, out_csv)
    return out_csv


def _icd10_category(code: str) -> str:
    """Coarse grouping by ICD-10-CM chapter-ish ranges."""
    c = code[:3]
    if c.startswith("C") or c.startswith("D0") or c.startswith("D1") \
            or c.startswith("D2") or c.startswith("D3") or c.startswith("D4"):
        return "neoplasm"
    if c.startswith("D5") or c.startswith("D6") or c.startswith("D7") or c.startswith("D8"):
        return "blood"
    if c.startswith("E"):
        return "endocrine"
    if c.startswith("I"):
        return "circulatory"
    if c.startswith("J"):
        return "respiratory"
    if c.startswith("K"):
        return "digestive"
    if c.startswith("N"):
        return "genitourinary"
    if c.startswith("R"):
        return "symptom"
    if c.startswith("T"):
        return "injury"
    if c.startswith("Z"):
        return "encounter"
    return "other"


# ---------------------------------------------------------------------------
# LOINC
# ---------------------------------------------------------------------------

def install_loinc(loinc_csv: Path, out_dir: Path) -> Path:
    """Normalize a user-supplied LOINC Loinc.csv into the registry format."""
    if not loinc_csv.exists():
        raise FileNotFoundError(f"LOINC CSV not found: {loinc_csv}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "loinc_full.csv"
    logger.info("Normalizing LOINC from %s", loinc_csv)
    n = 0
    with open(loinc_csv, newline="", encoding="utf-8-sig") as src, \
            open(out_csv, "w", newline="", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        writer = csv.writer(dst)
        writer.writerow(["code", "description", "category"])
        for row in reader:
            code = (row.get("LOINC_NUM") or row.get("LOINC_CODE") or "").strip()
            desc = (row.get("LONG_COMMON_NAME") or row.get("COMPONENT") or "").strip()
            category = (row.get("CLASS") or "").strip() or None
            status = (row.get("STATUS") or "").strip().upper()
            # Skip deprecated entries.
            if status and status not in ("ACTIVE", "TRIAL", "DISCOURAGED", ""):
                continue
            if not code or not desc:
                continue
            writer.writerow([code, desc, category or ""])
            n += 1
    logger.info("Wrote %d LOINC rows to %s", n, out_csv)
    return out_csv


# ---------------------------------------------------------------------------
# SNOMED CT
# ---------------------------------------------------------------------------

def install_snomed(snomed_dir: Path, out_dir: Path) -> Path:
    """Build a registry CSV from a SNOMED CT RF2 Snapshot Terminology dir.

    Uses the ``sct2_Description_Snapshot-en_*.txt`` file and keeps one
    preferred (fully-specified-name-free) description per active concept.
    """
    if not snomed_dir.exists():
        raise FileNotFoundError(f"SNOMED directory not found: {snomed_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "snomed_full.csv"

    desc_files = sorted(snomed_dir.glob("sct2_Description_Snapshot-en_*.txt"))
    if not desc_files:
        raise RuntimeError(
            "No sct2_Description_Snapshot-en_*.txt in directory; "
            "expected an RF2 Snapshot Terminology folder."
        )
    desc_file = desc_files[0]
    logger.info("Parsing SNOMED descriptions from %s", desc_file)
    # Keep one description per concept: prefer typeId 900000000000003001
    # (Fully specified name) only if no synonym; otherwise first synonym.
    SYNONYM = "900000000000013009"
    FSN = "900000000000003001"
    preferred: dict[str, str] = {}  # conceptId -> description
    fsn_only: dict[str, str] = {}
    with open(desc_file, encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            if row.get("active") != "1":
                continue
            concept = row.get("conceptId", "").strip()
            term = row.get("term", "").strip()
            type_id = row.get("typeId", "").strip()
            if not concept or not term:
                continue
            if type_id == SYNONYM and concept not in preferred:
                preferred[concept] = term
            elif type_id == FSN:
                fsn_only.setdefault(concept, term)
    n = 0
    with open(out_csv, "w", newline="", encoding="utf-8") as dst:
        writer = csv.writer(dst)
        writer.writerow(["code", "description", "category"])
        all_concepts = sorted(set(preferred) | set(fsn_only))
        for cid in all_concepts:
            desc = preferred.get(cid) or fsn_only.get(cid) or ""
            if not desc:
                continue
            writer.writerow([cid, desc, ""])
            n += 1
    logger.info("Wrote %d SNOMED rows to %s", n, out_csv)
    return out_csv


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--icd10",
        action="store_true",
        help="Download ICD-10-CM from CMS (public).",
    )
    parser.add_argument(
        "--icd10-url",
        default=DEFAULT_ICD10_URL,
        help="Override the CMS ICD-10-CM zip URL.",
    )
    parser.add_argument(
        "--loinc",
        type=Path,
        default=None,
        help="Path to a user-supplied Loinc.csv from LOINC's official release.",
    )
    parser.add_argument(
        "--snomed",
        type=Path,
        default=None,
        help="Path to a SNOMED CT RF2 Snapshot Terminology directory.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=MEDICAL_CODES_ROOT,
        help="Override the medical_codes root directory.",
    )
    args = parser.parse_args()

    did = False
    if args.icd10:
        download_icd10cm(args.icd10_url, args.out / "icd10cm" / "full")
        did = True
    if args.loinc is not None:
        install_loinc(args.loinc, args.out / "loinc" / "full")
        did = True
    if args.snomed is not None:
        install_snomed(args.snomed, args.out / "snomed" / "full")
        did = True

    if not did:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
