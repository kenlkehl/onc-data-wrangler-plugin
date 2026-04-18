"""Schema Registry: maps cancer site/histology to required site-specific data items.

Loads all configuration from ``data/ontologies/naaccr/schemas.yaml`` instead of
hardcoded Python dicts.  Implements the ``SchemaResolverLike`` protocol.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_SITE_PREFIX_RE = re.compile(r"^(C\d{2})", re.IGNORECASE)

# Default path to schemas.yaml relative to this file
_DEFAULT_SCHEMAS_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data"
    / "ontologies"
    / "naaccr"
    / "schemas.yaml"
)


class SchemaRegistry:
    """Maps primary site + histology -> cancer schema -> required SSDIs.

    All mapping tables are loaded from ``schemas.yaml`` at initialisation.
    Implements the ``SchemaResolverLike`` protocol via ``resolve_schema()``,
    ``get_schema_items()``, and ``get_schema_context()``.
    """

    def __init__(self, schemas_path: Path | None = None) -> None:
        self._schemas_path = schemas_path or _DEFAULT_SCHEMAS_PATH
        self._data: dict = {}

        # Populated by _load()
        self.CORE_STAGING_ITEMS: list[int] = []
        self.SCHEMA_SSDI_MAP: dict[str, list[int]] = {}
        self.SITE_SCHEMA_MAP: dict[str, str] = {}
        self._SITE_CONTEXT: dict[str, str] = {}
        self._SCHEMA_DISPLAY_NAMES: dict[str, str] = {}
        self._SCHEMA_ALIASES: dict[str, str] = {}
        self._PRIMARY_SITE_DESCRIPTIONS: dict[str, str] = {}

        # Hematologic histology ranges
        self._MELANOMA_HIST_LO: int = 8720
        self._MELANOMA_HIST_HI: int = 8790
        self._MYELOMA_HIST: tuple[int, int] = (9731, 9734)
        self._LYMPHOMA_HIST: tuple[int, int] = (9590, 9729)
        self._LEUKEMIA_HIST_LO: int = 9800
        self._LEUKEMIA_HIST_HI: int = 9948

        self._load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load all configuration from the schemas YAML file."""
        if not self._schemas_path.exists():
            logger.warning("Schemas file not found: %s", self._schemas_path)
            return

        with open(self._schemas_path, "r", encoding="utf-8") as fh:
            self._data = yaml.safe_load(fh) or {}

        self.CORE_STAGING_ITEMS = self._data.get("core_staging_items", [])
        self.SCHEMA_SSDI_MAP = self._data.get("schema_ssdi_map", {})
        self.SITE_SCHEMA_MAP = self._data.get("site_schema_map", {})
        self._SITE_CONTEXT = self._data.get("site_context", {})
        self._SCHEMA_DISPLAY_NAMES = self._data.get("schema_display_names", {})
        self._SCHEMA_ALIASES = self._data.get("schema_aliases", {})
        self._PRIMARY_SITE_DESCRIPTIONS = self._data.get("primary_site_descriptions", {})

        # Load hematologic histology ranges
        heme = self._data.get("hematologic_histology", {})
        if "melanoma" in heme:
            self._MELANOMA_HIST_LO = heme["melanoma"].get("low", self._MELANOMA_HIST_LO)
            self._MELANOMA_HIST_HI = heme["melanoma"].get("high", self._MELANOMA_HIST_HI)
        if "myeloma" in heme:
            self._MYELOMA_HIST = (heme["myeloma"]["low"], heme["myeloma"]["high"])
        if "lymphoma" in heme:
            self._LYMPHOMA_HIST = (heme["lymphoma"]["low"], heme["lymphoma"]["high"])
        if "leukemia" in heme:
            self._LEUKEMIA_HIST_LO = heme["leukemia"].get("low", self._LEUKEMIA_HIST_LO)
            self._LEUKEMIA_HIST_HI = heme["leukemia"].get("high", self._LEUKEMIA_HIST_HI)

        logger.info(
            "SchemaRegistry loaded: %d schemas, %d site mappings from %s",
            len(self.SCHEMA_SSDI_MAP),
            len(self.SITE_SCHEMA_MAP),
            self._schemas_path,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_schema_for_site_histology(
        self,
        primary_site: str,
        histology: str,
        schema_discriminator: Optional[str] = None,
    ) -> str:
        """Determine schema from ICD-O-3 topography + morphology."""
        prefix = self._normalize_site_prefix(primary_site)
        if not prefix:
            return self._check_heme_histology(histology)

        schema = self.SITE_SCHEMA_MAP.get(prefix)
        if schema is None:
            return self._check_heme_histology(histology)

        # Special case: skin (C44) requires melanoma histology
        if prefix == "C44":
            hist_num = self._parse_histology(histology)
            if hist_num is None or not (
                self._MELANOMA_HIST_LO <= hist_num <= self._MELANOMA_HIST_HI
            ):
                return "generic"

        return schema

    def _check_heme_histology(self, histology: str) -> str:
        """Check if histology indicates a hematologic malignancy."""
        hist_num = self._parse_histology(histology)
        if hist_num is None:
            return "generic"
        if self._MYELOMA_HIST[0] <= hist_num <= self._MYELOMA_HIST[1]:
            return "myeloma"
        if self._LYMPHOMA_HIST[0] <= hist_num <= self._LYMPHOMA_HIST[1]:
            return "lymphoma"
        if self._LEUKEMIA_HIST_LO <= hist_num <= self._LEUKEMIA_HIST_HI:
            return "leukemia"
        return "generic"

    def get_required_ssdis(self, schema: str) -> list[int]:
        """Return site-specific data item numbers for a schema."""
        # Resolve aliases (e.g., 'colorectal' -> 'colon_rectum')
        resolved = self._SCHEMA_ALIASES.get(schema, schema)
        return list(self.SCHEMA_SSDI_MAP.get(resolved, []))

    def get_all_staging_items(self, schema: str) -> list[int]:
        """Return core staging items + schema-specific SSDIs, deduplicated."""
        core = list(self.CORE_STAGING_ITEMS)
        ssdis = self.get_required_ssdis(schema)
        seen: set[int] = set(core)
        combined = list(core)
        for item_num in ssdis:
            if item_num not in seen:
                seen.add(item_num)
                combined.append(item_num)
        return combined

    def get_site_context(self, schema: str) -> str:
        """Return site-specific extraction guidance for prompts."""
        resolved = self._SCHEMA_ALIASES.get(schema, schema)
        context = self._SITE_CONTEXT.get(resolved)
        if context:
            return context
        return (
            "Extract all available staging information including TNM stage, "
            "Summary Stage 2018, EOD fields, tumor size, regional lymph node "
            "status, and any biomarkers or prognostic factors mentioned."
        )

    def get_display_name(self, schema: str) -> str:
        """Return human-readable name for a schema."""
        return self._SCHEMA_DISPLAY_NAMES.get(schema, schema)

    def get_primary_site_description(self, schema: str) -> str:
        """Return anatomical description for a schema."""
        resolved = self._SCHEMA_ALIASES.get(schema, schema)
        return self._PRIMARY_SITE_DESCRIPTIONS.get(resolved, "cancer")

    # ------------------------------------------------------------------
    # SchemaResolverLike protocol
    # ------------------------------------------------------------------

    def resolve_schema(self, context: dict[str, str]) -> str:
        """SchemaResolverLike protocol: resolve schema from context dict."""
        return self.get_schema_for_site_histology(
            context.get("primary_site", ""),
            context.get("histology", ""),
            context.get("schema_discriminator"),
        )

    def get_schema_items(self, schema: str) -> list[str]:
        """SchemaResolverLike protocol: return field_ids for schema."""
        return [str(n) for n in self.get_all_staging_items(schema)]

    def get_schema_context(self, schema: str) -> str:
        """SchemaResolverLike protocol: alias for get_site_context."""
        return self.get_site_context(schema)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_site_prefix(primary_site: str) -> Optional[str]:
        if not primary_site:
            return None
        cleaned = primary_site.strip().replace(" ", "")
        m = _SITE_PREFIX_RE.match(cleaned)
        if m:
            return m.group(1).upper()
        return None

    @staticmethod
    def _parse_histology(histology: str) -> Optional[int]:
        if not histology:
            return None
        cleaned = histology.strip().split("/")[0].strip()
        try:
            return int(cleaned)
        except (ValueError, TypeError):
            return None
