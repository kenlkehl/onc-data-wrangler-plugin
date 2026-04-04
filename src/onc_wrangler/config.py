"""YAML-based project configuration for Talk-to-Data pipelines."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class LLMConfig:
    """Configuration for an LLM backend."""
    provider: str = "openai"
    model: str = "gpt-oss-120b"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    max_tokens: int = 16384
    temperature: float = 0.0
    vertex_project: Optional[str] = None
    vertex_region: str = "us-east5"
    azure_api_version: str = "2024-12-01-preview"
    reasoning_marker: Optional[str] = None
    timeout: int = 300

    def resolve_api_key(self) -> str:
        """Resolve API key from config or environment variables."""
        if self.api_key:
            return self.api_key
        if self.provider == "anthropic":
            return os.environ.get("ANTHROPIC_API_KEY", "")
        if self.provider == "vertex":
            return ""
        if self.provider == "azure":
            return os.environ.get("AZURE_OPENAI_API_KEY", "")
        if self.provider == "openai":
            return os.environ.get("OPENAI_API_KEY", "none")
        return "none"

    def resolve_vertex_project(self) -> str:
        """Resolve Vertex project from config or environment."""
        if self.vertex_project:
            return self.vertex_project
        return os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID", "")


@dataclass
class CohortStageConfig:
    """Configuration for the cohort definition stage."""
    patient_file: Optional[str] = None
    diagnosis_file: Optional[str] = None
    demographics_file: Optional[str] = None  # single file (legacy)
    demographics_files: list = field(default_factory=list)  # multiple files
    patient_id_column: str = "record_id"
    diagnosis_code_column: Optional[str] = None
    diagnosis_code_filter: list = field(default_factory=list)
    sex_column: Optional[str] = None
    race_column: Optional[str] = None
    ethnicity_column: Optional[str] = None
    birth_date_column: Optional[str] = None
    death_date_column: Optional[str] = None
    death_indicator_column: Optional[str] = None
    followup_date: str = "2025-07-01"
    id_prefix: str = "patient"


@dataclass
class ExtractionConfig:
    """Configuration for the extraction stage."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    ontology_ids: list[str] = field(default_factory=lambda: ["naaccr"])
    cancer_type: str = "generic"
    chunk_tokens: int = 40000
    overlap_tokens: int = 200
    max_retries: int = 10
    patient_workers: int = 8
    items_per_call: int = 50
    max_output_tokens: int = 16384
    patient_id_column: str = "record_id"
    notes_text_column: str = "text"
    notes_date_column: str = "date"
    notes_type_column: str = "note_type"
    notes_paths: list[str] = field(default_factory=list)
    claude_code_model: str = "opus"


@dataclass
class DatabaseConfig:
    """Configuration for the database creation stage."""
    record_id_prefix: str = "patient"
    min_non_missing: int = 10
    forbidden_output_columns: list[str] = field(default_factory=lambda: ["record_id"])
    deidentify_dates: bool = True


@dataclass
class QueryConfig:
    """Configuration for the query/MCP server stage."""
    min_cell_size: int = 10
    max_query_rows: int = 500
    max_output_fraction: float = 0.5
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8000
    privacy_mode: str = "aggregate-only"


@dataclass
class ProjectConfig:
    """Top-level project configuration."""
    name: str = "my_project"
    input_paths: list[str] = field(default_factory=list)
    output_dir: str = ""
    cohort: CohortStageConfig = field(default_factory=CohortStageConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    query: QueryConfig = field(default_factory=QueryConfig)
    max_budget_usd: float = 10.0
    field_mappings: dict[str, Any] = field(default_factory=dict)
    patient_id_columns: dict[str, str] = field(default_factory=dict)

    def get_patient_id_column(self, filename: str) -> str:
        """Get the patient ID column name for a specific file.

        Checks patient_id_columns by exact filename, then by stem,
        then falls back to cohort.patient_id_column.
        """
        if filename in self.patient_id_columns:
            return self.patient_id_columns[filename]
        stem = Path(filename).stem
        for key, col in self.patient_id_columns.items():
            if Path(key).stem == stem:
                return col
        return self.cohort.patient_id_column

    def validate(self) -> list:
        """Validate configuration, returning a list of error messages."""
        errors = []
        for p in self.input_paths:
            path = Path(p)
            if not path.exists():
                errors.append("Input path does not exist: " + p)
        if not self.name:
            errors.append("Project name is required")
        return errors

    def resolve_input_files(self, extensions: tuple = (".csv", ".parquet")) -> list:
        """Collect files across all input paths.

        For each entry in input_paths: if it's a file with a matching
        extension, include it directly; if it's a directory, glob for
        matching files. Results are deduplicated and sorted.
        """
        seen = set()
        files = []
        for p in self.input_paths:
            path = Path(p)
            if path.is_file():
                if path.suffix.lower() in extensions:
                    resolved = path.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        files.append(resolved)
            elif path.is_dir():
                for ext in extensions:
                    for f in path.glob("*" + ext):
                        resolved = f.resolve()
                        if resolved not in seen:
                            seen.add(resolved)
                            files.append(resolved)
        return sorted(files, key=lambda f: f.name)

    def resolve_notes_files(self, extensions: tuple = (".csv", ".parquet")) -> list:
        """Collect notes files across extraction.notes_paths.

        Same logic as resolve_input_files but uses the notes_paths list.
        """
        seen = set()
        files = []
        for p in self.extraction.notes_paths:
            path = Path(p)
            if path.is_file():
                if path.suffix.lower() in extensions:
                    resolved = path.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        files.append(resolved)
            elif path.is_dir():
                for ext in extensions:
                    for f in path.glob("*" + ext):
                        resolved = f.resolve()
                        if resolved not in seen:
                            seen.add(resolved)
                            files.append(resolved)
        return sorted(files, key=lambda f: f.name)

    def find_file(self, filename: str) -> Optional[Path]:
        """Search input paths for a file by name.

        If filename is an absolute path, return it directly (if it exists).
        Otherwise, search each directory in input_paths for the filename,
        and check if any file-type entry matches the filename.
        """
        fp = Path(filename)
        if fp.is_absolute():
            if fp.exists():
                return fp
            return None
        for p in self.input_paths:
            path = Path(p)
            if path.is_dir():
                candidate = path / filename
                if candidate.exists():
                    return candidate
            elif path.is_file() and path.name == filename:
                return path
        return None

    def output_path(self, *parts) -> Path:
        """Get a path within the output directory, creating it if needed."""
        p = Path(self.output_dir).joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_path(self) -> Path:
        """Path to the DuckDB database file."""
        return self.output_path(self.name + ".duckdb")

    @property
    def schema_path(self) -> Path:
        """Path to the generated schema metadata file."""
        return self.output_path("schema.md")

    @property
    def summary_path(self) -> Path:
        """Path to the generated summary statistics file."""
        return self.output_path("summary.md")

    @property
    def summary_stats_path(self) -> Path:
        """Path to the generated structured summary statistics JSON."""
        return self.output_path("summary_stats.json")


def _dict_to_llm_config(d: dict) -> LLMConfig:
    """Convert a dictionary to LLMConfig, ignoring unknown keys."""
    known = {f.name for f in LLMConfig.__dataclass_fields__.values()}
    return LLMConfig(**{k: v for k, v in d.items() if k in known})


def load_config(path: str) -> ProjectConfig:
    """Load a ProjectConfig from a YAML file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        Populated ProjectConfig instance.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError("Config file not found: " + str(path))

    with open(path) as f:
        raw = yaml.safe_load(f)

    project = raw.get("project", {})
    input_paths = project.get("input_paths", [])
    input_dir = project.get("input_dir", "")
    if not input_paths and input_dir:
        input_paths = [input_dir]

    config = ProjectConfig(
        name=project.get("name", "my_project"),
        input_paths=input_paths,
        output_dir=project.get("output_dir", ""),
        max_budget_usd=float(project.get("max_budget_usd", 10.0)),
    )

    # Cohort
    coh = raw.get("cohort", {})
    if coh:
        known_coh = {f.name for f in CohortStageConfig.__dataclass_fields__.values()}
        config.cohort = CohortStageConfig(**{k: v for k, v in coh.items() if k in known_coh})
        # Promote legacy demographics_file into demographics_files if needed
        if config.cohort.demographics_file and not config.cohort.demographics_files:
            config.cohort.demographics_files = [config.cohort.demographics_file]

    # Extraction
    ext = raw.get("extraction", {})
    if ext:
        llm_dict = ext.pop("llm", None)
        known_ext = {f.name for f in ExtractionConfig.__dataclass_fields__.values()}
        config.extraction = ExtractionConfig(**{k: v for k, v in ext.items() if k in known_ext})
        if llm_dict:
            config.extraction.llm = _dict_to_llm_config(llm_dict)

    # Database
    db = raw.get("database", {})
    if db:
        known_db = {f.name for f in DatabaseConfig.__dataclass_fields__.values()}
        config.database = DatabaseConfig(**{k: v for k, v in db.items() if k in known_db})

    # Query
    q = raw.get("query", {})
    if q:
        known_q = {f.name for f in QueryConfig.__dataclass_fields__.values()}
        config.query = QueryConfig(**{k: v for k, v in q.items() if k in known_q})

    # Field mappings
    config.field_mappings = raw.get("field_mappings", {}) or {}

    # Per-file patient ID columns
    config.patient_id_columns = raw.get("patient_id_columns", {}) or {}

    return config


def save_config(config: ProjectConfig, path: str):
    """Save a ProjectConfig to a YAML file."""
    import dataclasses

    # Keys that should never be serialized to disk
    _secret_keys = {"api_key"}

    def _to_dict(obj):
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {
                k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()
                if k not in _secret_keys
            }
        return obj

    data = {
        "project": {
            "name": config.name,
            "input_paths": config.input_paths,
            "output_dir": config.output_dir,
            "max_budget_usd": config.max_budget_usd,
        },
        "cohort": _to_dict(config.cohort),
        "extraction": _to_dict(config.extraction),
        "database": _to_dict(config.database),
        "query": _to_dict(config.query),
        "field_mappings": config.field_mappings,
        "patient_id_columns": config.patient_id_columns,
    }

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
