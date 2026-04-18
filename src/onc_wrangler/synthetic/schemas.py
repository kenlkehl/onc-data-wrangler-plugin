"""Table schema definitions for synthetic structured data generation."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class ColumnDef:
    """Definition of a single column in a structured table."""
    name: str
    type: str
    description: str


@dataclass
class TableSchema:
    """Schema for a structured output table."""
    name: str
    description: str
    columns: list[ColumnDef] = field(default_factory=list)
    generation_instructions: str = ""


def load_table_schemas(schema_dir: Path) -> list[TableSchema]:
    """Load all table schemas from YAML files in a directory.

    Each YAML file defines one table. New table types are added by
    dropping a new YAML file in the directory.
    """
    schema_dir = Path(schema_dir)
    schemas = []
    for yaml_path in sorted(schema_dir.glob("*.yaml")):
        with open(yaml_path) as f:
            raw = yaml.safe_load(f)
        columns = [
            ColumnDef(name=c["name"], type=c["type"], description=c["description"])
            for c in raw.get("columns", [])
        ]
        schema = TableSchema(
            name=raw["table_name"],
            description=raw.get("description", ""),
            columns=columns,
            generation_instructions=raw.get("generation_instructions", ""),
        )
        schemas.append(schema)
    return schemas


def schema_to_prompt_text(schema: TableSchema) -> str:
    """Format a table schema as prompt-friendly text for LLM instructions."""
    lines = [
        f"### Table: {schema.name}",
        f"Description: {schema.description}",
        "Columns:",
    ]
    for col in schema.columns:
        lines.append(f"  - {col.name} ({col.type}): {col.description}")
    if schema.generation_instructions:
        lines.append(f"Instructions: {schema.generation_instructions}")
    return "\n".join(lines)
