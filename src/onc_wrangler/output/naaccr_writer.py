"""Write NAACCR v26 output in XML, fixed-width flat file, or CSV format.

Ported from onc-registry-extraction/naaccr_pipeline/output/naaccr_writer.py.
Adapted to the mega_extractor interface where ``results`` is a flat dict of
``{patient_id: {item_number_str: resolved_code}}``.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement, indent

from ..ontologies.naaccr_dictionary import NAACCRDictionary

logger = logging.getLogger(__name__)

NAACCR_XML_NS = "http://naaccr.org/naaccrxml"
NAACCR_XML_SCHEMA = "http://naaccr.org/naaccrxml/naaccr-xml-v26.xsd"


class NAACCRWriter:
    """Produce NAACCR-formatted output files.

    Parameters
    ----------
    dictionary : NAACCRDictionary
        Loaded dictionary used to look up ``xml_id``, ``parent_element``,
        and field ``length`` for each item number.
    """

    def __init__(self, dictionary: NAACCRDictionary) -> None:
        self._dict = dictionary

    # ------------------------------------------------------------------
    # XML
    # ------------------------------------------------------------------

    def write_xml(
        self,
        results: dict[str, dict[str, str]],
        output_path: Path,
    ) -> None:
        """Write NAACCR XML (NaaccrData > Patient > Tumor hierarchy).

        Parameters
        ----------
        results : dict[str, dict[str, str]]
            ``{patient_id: {item_number_str: resolved_code}}``.
        output_path : Path
            Destination file path.
        """
        output_path = Path(output_path)
        root = Element(
            "NaaccrData",
            xmlns=NAACCR_XML_NS,
        )

        for patient_id, items in results.items():
            patient_el = SubElement(root, "Patient")

            # NaaccrData-level items (file-level attributes) are added once
            # from the first patient.
            if patient_el is root[0]:
                self._add_items(root, items, parent_filter="NaaccrData")

            # Patient-level items
            self._add_items(patient_el, items, parent_filter="Patient")

            # Tumor-level items go under a single Tumor element per patient.
            tumor_el = SubElement(patient_el, "Tumor")
            self._add_items(tumor_el, items, parent_filter="Tumor")

        indent(root, space="  ")
        tree = ElementTree(root)
        tree.write(
            str(output_path), encoding="UTF-8", xml_declaration=True,
        )
        logger.info("NAACCR XML written to %s", output_path)

    # ------------------------------------------------------------------
    # Flat file
    # ------------------------------------------------------------------

    def write_flat_file(
        self,
        results: dict[str, dict[str, str]],
        output_path: Path,
    ) -> None:
        """Write a simplified NAACCR-style fixed-width flat file.

        Each patient's items are written as a single fixed-width line.
        Items are sorted by item number and right-padded (or truncated)
        to the dictionary-defined field length.

        Parameters
        ----------
        results : dict[str, dict[str, str]]
            ``{patient_id: {item_number_str: resolved_code}}``.
        output_path : Path
            Destination file path.
        """
        output_path = Path(output_path)

        # Collect all item numbers across every patient, sorted.
        all_items = sorted(
            {int(n) for items in results.values() for n in items},
        )

        with open(output_path, "w", encoding="utf-8") as fh:
            for items in results.values():
                parts: list[str] = []
                for item_num in all_items:
                    item_def = self._dict.get_item(item_num)
                    length = item_def.length if item_def else 1
                    value = items.get(str(item_num), "")
                    # Left-justify, pad/truncate to field length.
                    parts.append(value[:length].ljust(length))
                fh.write("".join(parts) + "\n")

        logger.info("NAACCR flat file written to %s", output_path)

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------

    def write_csv(
        self,
        results: dict[str, dict[str, str]],
        output_path: Path,
    ) -> None:
        """Write one CSV row per patient with item names as column headers.

        Parameters
        ----------
        results : dict[str, dict[str, str]]
            ``{patient_id: {item_number_str: resolved_code}}``.
        output_path : Path
            Destination file path.
        """
        output_path = Path(output_path)

        # Collect all item numbers across every patient, sorted.
        all_items = sorted(
            {int(n) for items in results.values() for n in items},
        )

        headers: list[str] = []
        for item_num in all_items:
            item_def = self._dict.get_item(item_num)
            name = item_def.name if item_def else f"Item_{item_num}"
            headers.append(f"{name} [{item_num}]")

        with open(output_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(headers)
            for items in results.values():
                row = [items.get(str(item_num), "") for item_num in all_items]
                writer.writerow(row)

        logger.info("CSV written to %s", output_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_items(
        self,
        parent_el: Element,
        items: dict[str, str],
        parent_filter: str,
    ) -> None:
        """Add ``<Item>`` sub-elements for items matching *parent_filter*."""
        for item_num_str in sorted(items, key=lambda k: int(k)):
            item_num = int(item_num_str)
            item_def = self._dict.get_item(item_num)
            if item_def is None:
                continue
            if item_def.parent_element != parent_filter:
                continue
            value = items[item_num_str]
            if not value:
                continue
            item_el = SubElement(parent_el, "Item")
            item_el.set("naaccrId", item_def.xml_id)
            item_el.set("naaccrNum", str(item_num))
            item_el.text = value
