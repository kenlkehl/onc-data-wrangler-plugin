"""Load and index the NAACCR v26 data dictionary from CSV files.

Adapted from the mega_extractor NAACCR dictionary loader.
Loads CSV files from the plugin's data/ontologies/naaccr/codes/ directory.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default to the plugin's data directory
_PLUGIN_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "ontologies" / "naaccr" / "codes"


@dataclass
class NAACCRDataItem:
    """A single NAACCR data-dictionary item."""

    item_number: int
    name: str
    length: int
    source_of_standard: str
    record_type: str
    section: str
    xml_id: str
    parent_element: str
    year_implemented: str
    version_implemented: str
    year_retired: str
    version_retired: str
    npcr_collect: str
    coc_collect: str
    seer_collect: str
    cccr_collect: str
    description: str
    instructions: str
    allowable_values: str
    data_type: str
    format_spec: str
    alternate_names: list[str] = field(default_factory=list)

    @property
    def field_id(self) -> str:
        return str(self.item_number)

    @property
    def prompt_field_name(self) -> str:
        return self.xml_id if self.xml_id else f"item_{self.item_number}"


@dataclass
class CodeEntry:
    """One valid code for a data item."""

    item_number: int
    item_name: str
    length: int
    code: str
    description: str


def _is_valid_item_number(value: str) -> bool:
    try:
        int(value)
        return True
    except (ValueError, TypeError):
        return False


def _safe_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


class NAACCRDictionary:
    """In-memory index of the NAACCR v26 data dictionary."""

    def __init__(self, data_dir: Optional[str | Path] = None) -> None:
        self._data_dir = Path(data_dir) if data_dir else _PLUGIN_DATA_DIR
        self._items_by_number: dict[int, NAACCRDataItem] = {}
        self._items_by_section: dict[str, list[NAACCRDataItem]] = {}
        self._codes_by_item: dict[int, list[CodeEntry]] = {}
        self._items_by_alt_name: dict[str, NAACCRDataItem] = {}
        self._loaded = False

    def load(self) -> None:
        """Parse all three CSV files and build look-up indexes."""
        self._load_data_items()
        self._load_code_list()
        self._load_alternate_names()
        self._loaded = True
        logger.info(
            "NAACCR dictionary loaded: %d items, %d code entries",
            len(self._items_by_number),
            sum(len(v) for v in self._codes_by_item.values()),
        )

    def _read_csv_lines(self, filename: str) -> list[str]:
        path = self._data_dir / filename
        with open(path, newline="", encoding="utf-8-sig") as fh:
            lines = fh.readlines()
        if lines and lines[0].strip() == "":
            lines = lines[1:]
        return lines

    def _load_data_items(self) -> None:
        lines = self._read_csv_lines("DataItems.csv")
        reader = csv.DictReader(lines)
        for row in reader:
            raw_num = row.get("Data Item Number", "").strip()
            if not _is_valid_item_number(raw_num):
                continue
            item_number = int(raw_num)
            item = NAACCRDataItem(
                item_number=item_number,
                name=row.get("Data Item Name", "").strip(),
                length=_safe_int(row.get("Length", "").strip()),
                source_of_standard=row.get("Source of Standard", "").strip(),
                record_type=row.get("Record Type", "").strip(),
                section=row.get("Section Name", "").strip(),
                xml_id=row.get("XML NAACCR ID", "").strip(),
                parent_element=row.get("Parent XML Element", "").strip(),
                year_implemented=row.get("Year Implemented", "").strip(),
                version_implemented=row.get("Version Implemented", "").strip(),
                year_retired=row.get("Year Retired", "").strip(),
                version_retired=row.get("Version Retired", "").strip(),
                npcr_collect=row.get("NPCR Collect", "").strip(),
                coc_collect=row.get("CoC Collect", "").strip(),
                seer_collect=row.get("SEER Collect", "").strip(),
                cccr_collect=row.get("CCCR Collect", "").strip(),
                description=row.get("Description", "").strip(),
                instructions=row.get("Instructions for Coding", "").strip(),
                allowable_values=row.get("Allowable Values", "").strip(),
                data_type=row.get("Data Type", "").strip(),
                format_spec=row.get("Format", "").strip(),
            )
            self._items_by_number[item_number] = item
            self._items_by_section.setdefault(item.section, []).append(item)

    def _load_code_list(self) -> None:
        lines = self._read_csv_lines("CodeList.csv")
        reader = csv.DictReader(lines)
        for row in reader:
            raw_num = row.get("Data Item Number", "").strip()
            if not _is_valid_item_number(raw_num):
                continue
            entry = CodeEntry(
                item_number=int(raw_num),
                item_name=row.get("Data Item Name", "").strip(),
                length=_safe_int(row.get("Length", "").strip()),
                code=row.get("Code", "").strip(),
                description=row.get("Description", "").strip(),
            )
            self._codes_by_item.setdefault(entry.item_number, []).append(entry)

    def _load_alternate_names(self) -> None:
        lines = self._read_csv_lines("AlternateNames.csv")
        reader = csv.DictReader(lines)
        for row in reader:
            raw_num = row.get("Data Item Number", "").strip()
            if not _is_valid_item_number(raw_num):
                continue
            item_number = int(raw_num)
            alt_name = row.get("Alternate Name", "").strip()
            if not alt_name:
                continue
            item = self._items_by_number.get(item_number)
            if item is not None:
                item.alternate_names.append(alt_name)
                self._items_by_alt_name[alt_name.lower()] = item

    def get_item(self, item_number: int) -> Optional[NAACCRDataItem]:
        return self._items_by_number.get(item_number)

    def get_items_by_section(self, section: str) -> list[NAACCRDataItem]:
        return list(self._items_by_section.get(section, []))

    def get_codes(self, item_number: int) -> list[CodeEntry]:
        return list(self._codes_by_item.get(item_number, []))

    def get_active_items(self) -> list[NAACCRDataItem]:
        return [item for item in self._items_by_number.values() if not item.year_retired]

    @property
    def all_sections(self) -> list[str]:
        return sorted(self._items_by_section.keys())
