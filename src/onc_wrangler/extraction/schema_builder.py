"""Build prompt-level JSON format instructions from data dictionary items.

Ported from onc-registry-extraction/naaccr_pipeline/llm/structured_output.py.
Generalized to work with any ontology via the ``DictionaryItemLike`` and
``CodeResolverLike`` protocols.

Instead of constrained decoding (guided_json), we describe the expected JSON
format in the prompt text and let the LLM produce free-form JSON, retrying on
parse failure.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SchemaBuilder:
    """Builds prompt-level JSON format instructions from data items.

    Generates text blocks that tell the LLM what JSON structure to produce,
    including field names, valid codes, and format expectations.
    """

    def build_json_format_instructions(
        self,
        items: list[Any],
        code_resolver: Any,
    ) -> str:
        r"""Generate prompt text describing the expected JSON output format.

        Parameters
        ----------
        items:
            Data item objects satisfying ``DictionaryItemLike``:
            ``prompt_field_name``, ``name``, ``field_id``, ``length``,
            ``data_type``, ``allowable_values``.
        code_resolver:
            Object satisfying ``CodeResolverLike``:
            ``get_valid_codes_prompt(field_id) -> str``.

        Returns
        -------
        str
            A text block to embed in the prompt describing expected JSON.
        """
        field_lines: list[str] = []
        for item in items:
            field_name = self._field_name(item)
            desc = self._field_description(item, code_resolver)
            field_lines.append(f'- "{field_name}": {desc}')

        fields_block = "\n".join(field_lines)

        return (
            "Respond with a JSON object. For each item, provide an object with:\n"
            '  "value": the extracted value (use valid codes listed below),\n'
            '  "confidence": a float 0.0-1.0 indicating extraction confidence,\n'
            '  "evidence": a short quote (max 200 chars) from the text supporting the value.\n'
            "\n"
            "If information is not found in the text, set value to the appropriate "
            '"unknown" code (e.g. "9", "99", "unknown") and confidence to 0.0.\n'
            "\n"
            f"Expected fields:\n{fields_block}"
        )

    def build_simple_schema(self, fields: dict[str, dict]) -> dict:
        """Build a JSON schema dict for simple extractions."""
        return {
            "type": "object",
            "properties": fields,
            "required": list(fields.keys()),
        }

    # -- internal helpers -------------------------------------------------

    @staticmethod
    def _field_name(item: Any) -> str:
        """Derive the JSON field name from a data item."""
        # Try prompt_field_name first (DictionaryItemLike protocol)
        pfn = getattr(item, "prompt_field_name", None)
        if pfn:
            return pfn

        # NAACCR items: use xml_id
        xml_id = getattr(item, "xml_id", None)
        if xml_id and str(xml_id).strip():
            return str(xml_id).strip()

        # Generic items: use json_field or id
        json_field = getattr(item, "json_field", None)
        if json_field:
            return json_field

        item_id = getattr(item, "id", None) or getattr(item, "field_id", "unknown")
        return str(item_id)

    @staticmethod
    def _field_description(item: Any, code_resolver: Any) -> str:
        """Build a human-readable description for one field."""
        field_id = getattr(item, "field_id", "") or getattr(item, "id", "")
        item_name = getattr(item, "name", "") or ""
        item_length = getattr(item, "length", 0) or 0
        data_type = (getattr(item, "data_type", "") or "").strip().lower()
        description = getattr(item, "description", "") or ""

        # Try to get valid codes prompt from resolver
        codes_text = ""
        if code_resolver is not None:
            try:
                codes_text = code_resolver.get_valid_codes_prompt(str(field_id))
            except Exception:
                pass

        # Check for extraction hints (generic ontologies)
        hints = getattr(item, "extraction_hints", None)
        hints_text = ""
        if hints and isinstance(hints, list) and len(hints) > 0:
            hints_text = f"Look for: {', '.join(hints[:5])}"

        # Item number for NAACCR items
        item_number = getattr(item, "item_number", None)
        name_part = item_name
        if item_number is not None:
            name_part = f"{item_name} (Item {item_number})"

        parts = [name_part]

        if description and len(description) < 200:
            parts.append(description)

        if codes_text:
            parts.append(codes_text)
        elif data_type == "date":
            parts.append("YYYYMMDD format (use 99 for unknown day/month)")
        elif data_type == "digits":
            allowable = getattr(item, "allowable_values", "") or ""
            parts.append(f"{item_length}-digit number. {allowable}".strip())
        elif item_length > 0:
            parts.append(f"max {item_length} characters")

        if hints_text:
            parts.append(hints_text)

        return ". ".join(p for p in parts if p)
