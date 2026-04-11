"""Build a DuckDB database from extracted and harmonized data.

Creates tables for each data category (diagnosis, biomarker, etc.)
plus a cohort table. Applies de-identification and filtering.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

from ..config import ProjectConfig

logger = logging.getLogger(__name__)

# Substrings matched case-insensitively to detect PII columns
_PII_COLUMN_SUBSTRINGS = {"mrn", "ssn", "phone", "email", "address", "zip_code", "postal"}

# Exact column names (compared case-insensitively) that are PII
_PII_COLUMN_NAMES_LOWER = {
    "last_nm", "first_nm", "middle_nm",
    "last_name", "first_name", "middle_name",
    "patient_name", "full_name",
    "dob", "date_of_birth",
    "street", "city", "state", "zip", "county",
    "phone_number", "email_address", "fax",
    "insurance_id", "policy_number",
}


def _strip_pii_columns(
    df: pd.DataFrame, extra_id_columns: set[str] | None = None
) -> pd.DataFrame:
    """Remove columns that may contain PII (MRNs, patient names, etc.).

    Acts as a safety net to prevent real identifiers from leaking into
    the final de-identified database.  Also strips any columns listed in
    *extra_id_columns* (the configured patient ID column names).
    """
    cols_to_drop = []
    for col in df.columns:
        lower = col.lower()
        if lower in _PII_COLUMN_NAMES_LOWER:
            cols_to_drop.append(col)
        elif any(pattern in lower for pattern in _PII_COLUMN_SUBSTRINGS):
            cols_to_drop.append(col)
        elif extra_id_columns and col in extra_id_columns:
            cols_to_drop.append(col)
    if cols_to_drop:
        logger.warning(
            "Stripping PII columns: %s", sorted(cols_to_drop)
        )
        df = df.drop(columns=cols_to_drop)
    return df


def _load_cohort_ids(output_dir: str) -> list | None:
    """Load original cohort patient IDs, or None if not available."""
    path = Path(output_dir) / "cohort_ids.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def filter_columns_by_non_missing(
    df: pd.DataFrame, min_non_missing: int = 10
) -> pd.DataFrame:
    """Remove columns where fewer than min_non_missing values are non-null."""
    cols_to_keep = [
        col for col in df.columns if df[col].notna().sum() >= min_non_missing
    ]
    dropped = set(df.columns) - set(cols_to_keep)
    if dropped:
        logger.info("Dropped columns with fewer than %d non-missing values: %s",
                     min_non_missing, sorted(dropped))
    return df[cols_to_keep]


def _deidentify_ids(
    df: pd.DataFrame,
    id_column: str,
    prefix: str,
    id_map: dict = None,
) -> pd.DataFrame:
    """Replace real IDs with sequential anonymized IDs.

    If id_map is None, builds a fresh mapping from IDs in this DataFrame.
    """
    df = df.copy()
    if id_map is None:
        unique_ids = sorted(df[id_column].dropna().unique())
        id_map = {
            old_id: f"{prefix}_{i:06d}"
            for i, old_id in enumerate(unique_ids, start=1)
        }
    # id_map keys are always strings; ensure the column is string-typed
    # so that integer IDs from structured data match correctly.
    df[id_column] = df[id_column].astype(str).map(id_map)
    return df


def _sanitize_table_name(name: str) -> str:
    """Convert a category name to a valid SQL table name."""
    name = name.lower().replace(" ", "_").replace("-", "_")
    name = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
    if not name:
        return "unknown"
    if name[0].isdigit():
        name = "t_" + name
    return name


def _category_from_harmonized_stem(
    stem: str, known_categories: list[str]
) -> str:
    """Extract the category from a harmonized filename stem.

    Harmonized files are named ``{source_stem}_{category}.parquet``.
    Since both the source stem and the category can contain underscores,
    we match against *known_categories* (longest first) to find the
    correct suffix.  Falls back to the **full stem** as the category
    if no known category matches — this prevents unrelated files that
    happen to share a suffix (e.g. ``imaging_assessments`` and
    ``med_onc_assessments``) from colliding into the same table.
    """
    # Try longest categories first so e.g. "cancer_systemic_therapy_regimen"
    # matches before "regimen".
    for cat in sorted(known_categories, key=len, reverse=True):
        if stem.endswith("_" + cat) or stem == cat:
            return cat
    # Fallback: use the full stem as the category to avoid collisions
    return stem


def _table_name_from_category(category: str) -> str:
    """Convert an extraction/harmonization category to a database table name.

    Strips common prefixes like 'cancer_' and normalizes the name.
    This is the canonical function used by both the database builder and
    the propose_tables stage to ensure consistent naming.
    """
    name = category.lower().strip()
    for prefix in ("cancer_",):
        if name.startswith(prefix):
            name = name[len(prefix):]

    name = name.replace("_therapy_regimen", "").replace("_therapy", "")
    name = "_".join(name.split(" ")).replace("-", "_")
    name = "".join(c if c.isalnum() else "_" for c in name)

    if name and name[0].isdigit():
        name = "t_" + name

    return name or "unknown"


def _table_exists(con, table_name: str) -> bool:
    """Check if a table already exists in the database."""
    result = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_name = ? AND table_schema = 'main'",
        [table_name],
    ).fetchone()
    return result[0] > 0


def _insert_aligned(con, table_name: str, df: pd.DataFrame):
    """Insert a DataFrame into an existing table, aligning columns.

    Adds any new columns from the DataFrame to the table, and fills
    missing columns with NULL so that schemas always match.
    """
    existing_cols = [
        row[0]
        for row in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = ? AND table_schema = 'main'",
            [table_name],
        ).fetchall()
    ]

    # Add columns that exist in the DataFrame but not in the table
    for col in df.columns:
        if col not in existing_cols:
            con.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "{col}" VARCHAR')
            existing_cols.append(col)

    # Build SELECT with NULLs for columns missing from the DataFrame
    select_parts = []
    for col in existing_cols:
        if col in df.columns:
            select_parts.append(f'"{col}"')
        else:
            select_parts.append(f'NULL AS "{col}"')

    select_clause = ", ".join(select_parts)
    con.execute(f'INSERT INTO "{table_name}" SELECT {select_clause} FROM df')


# Columns allowed in the final cohort table.  Everything else from the
# source patient/demographics files is dropped.
_COHORT_ALLOWED_COLUMNS = {
    "record_id",
    "sex", "race", "ethnicity",
    "died_yes_or_no",
    "birth_date",  # kept temporarily; dropped before DB insertion
    "birth_to_last_followup_or_death_years",
    "birth_to_death_years",
}


class DatabaseBuilder:
    """Build a DuckDB database from extracted and harmonized data.

    Creates tables for each data category (diagnosis, biomarker, etc.)
    plus a cohort table. Applies de-identification and filtering.
    """

    def __init__(self, config: ProjectConfig):
        self.config = config
        self.output_dir = Path(config.output_dir)
        self.db_path = config.db_path
        self.record_id_prefix = config.database.record_id_prefix
        self.min_non_missing = config.database.min_non_missing
        self.deidentify_dates = config.database.deidentify_dates
        self._birth_dates = None
        self._approved_tables: set[str] | None = None
        self._original_id_columns = self._collect_original_id_columns()

    def _collect_original_id_columns(self) -> set[str]:
        """Collect all configured patient ID column names to strip.

        These are the *original* column names from source files that should
        never appear in the final database (the de-identified ``record_id``
        replaces them).
        """
        id_cols: set[str] = set()
        id_cols.add(self.config.cohort.patient_id_column)
        id_cols.add(self.config.extraction.patient_id_column)
        for col in self.config.patient_id_columns.values():
            id_cols.add(col)
        # "record_id" is the standardized de-identified name — keep it
        id_cols.discard("record_id")
        return id_cols

    def _rename_id_column(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rename the original patient ID column to ``record_id``.

        Checks each configured patient ID column name; the first one found
        in the DataFrame is renamed so that downstream de-identification
        and linkage work correctly.
        """
        if "record_id" in df.columns:
            return df
        for id_col in self._original_id_columns:
            if id_col in df.columns:
                logger.info("Renaming patient ID column '%s' -> 'record_id'", id_col)
                return df.rename(columns={id_col: "record_id"})
        return df

    def build(self) -> Path:
        """Build the full database. Returns Path to the created DuckDB file."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if self.db_path.exists():
            logger.info("Removing existing database: %s", self.db_path)
            self.db_path.unlink()

        # Load proposed tables for gating (if available)
        self._approved_tables = self._load_proposed_tables()

        id_map = self._collect_all_patient_ids()

        if self.deidentify_dates:
            self._birth_dates = self._load_birth_dates(id_map)

        con = duckdb.connect(str(self.db_path))
        try:
            self._load_cohort(con, id_map)
            self._load_extractions(con, id_map)
            self._load_harmonized(con, id_map)
            self._log_summary(con)
        finally:
            con.close()

        logger.info("Database built: %s", self.db_path)
        return self.db_path

    def _load_proposed_tables(self) -> set[str] | None:
        """Load approved table names from proposed_tables.json.

        Returns the set of approved table names, or None if the file
        doesn't exist (in which case all tables are created).
        """
        proposal_path = self.output_dir / "proposed_tables.json"
        if not proposal_path.exists():
            logger.info("No proposed_tables.json found; creating all tables")
            return None
        with open(proposal_path) as f:
            proposed = json.load(f)
        approved = set(proposed.keys())
        logger.info("Loaded %d approved tables from proposed_tables.json: %s",
                     len(approved), sorted(approved))
        return approved

    def _is_table_approved(self, table_name: str) -> bool:
        """Check if a table name is in the approved set."""
        if self._approved_tables is None:
            return True
        return table_name in self._approved_tables

    def _collect_all_patient_ids(self) -> dict[str, str]:
        """Build a consistent original-ID -> de-identified-ID mapping.

        If the cohort stage was run, its id_map is reconstructed from
        cohort_ids.json (the original IDs saved by the pipeline).  This
        ensures extraction and harmonized data use the same de-identified
        IDs as the cohort table.

        If no cohort_ids.json exists (cohort stage was skipped), IDs are
        collected from extraction shards and harmonized files and a fresh
        mapping is created.
        """
        cohort_ids = _load_cohort_ids(str(self.output_dir))
        if cohort_ids:
            # Reconstruct the same mapping the CohortBuilder used
            sorted_ids = sorted(set(str(x) for x in cohort_ids), key=str)
            id_map = {
                old_id: f"{self.record_id_prefix}_{i:06d}"
                for i, old_id in enumerate(sorted_ids, start=1)
            }
            logger.info("Reconstructed cohort id_map: %d patients", len(id_map))
            return id_map

        # Fallback: no cohort stage — collect from extraction/harmonized data
        all_ids = set()

        extractions_dir = self.output_dir / "extractions"
        extractions_file = extractions_dir / "extractions.parquet"
        if extractions_file.exists():
            df = pd.read_parquet(extractions_file)
            if "patient_id" in df.columns:
                all_ids.update(df["patient_id"].dropna().unique())

        harmonized_dir = self.output_dir / "harmonized"
        if harmonized_dir.exists():
            for parquet_file in sorted(harmonized_dir.glob("*.parquet")):
                df = pd.read_parquet(parquet_file)
                # Check for record_id or any configured patient ID column
                if "record_id" in df.columns:
                    all_ids.update(df["record_id"].dropna().unique())
                else:
                    for id_col in self._original_id_columns:
                        if id_col in df.columns:
                            all_ids.update(df[id_col].dropna().unique())
                            break

        sorted_ids = sorted(str(i) for i in all_ids)
        id_map = {
            old_id: f"{self.record_id_prefix}_{i:06d}"
            for i, old_id in enumerate(sorted_ids, start=1)
        }
        logger.info("Collected %d unique patient IDs (no cohort)", len(id_map))
        return id_map

    def _load_birth_dates(self, id_map: dict) -> Optional[dict]:
        """Load birth dates from cohort for date de-identification.

        Returns a mapping from de-identified record_id to birth_date.
        The cohort file already has de-identified record_ids and birth_date,
        so we can build the mapping directly.
        """
        cohort_parquet = self.output_dir / "cohort.parquet"
        cohort_csv = self.output_dir / "cohort.csv"

        if cohort_parquet.exists():
            df = pd.read_parquet(cohort_parquet)
        elif cohort_csv.exists():
            df = pd.read_csv(cohort_csv)
        else:
            logger.warning("No cohort file found for birth date loading")
            return None

        if "record_id" not in df.columns or "birth_date" not in df.columns:
            logger.warning(
                "Cohort file missing 'record_id' or 'birth_date' columns"
            )
            return None

        df["birth_date"] = pd.to_datetime(df["birth_date"], errors="coerce")

        # Cohort file already contains de-identified record_ids
        birth_dates = {}
        for _, row in df.iterrows():
            record_id = str(row["record_id"])
            if pd.notna(row["birth_date"]):
                birth_dates[record_id] = row["birth_date"]

        logger.info("Loaded %d birth dates for date de-identification",
                     len(birth_dates))
        return birth_dates

    def _deidentify_dates_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert date columns to years_since_birth and calendar_year.

        For each date column: adds {col}_years_since_birth (float),
        {col}_calendar_year (Int64). Drops the original date column.
        Requires record_id column and pre-loaded birth dates.
        """
        if self._birth_dates is None or "record_id" not in df.columns:
            return df

        skip_columns = {"record_id", "category", "source", "birth_date", "data_source"}
        date_cols = []

        for col in df.columns:
            if col in skip_columns:
                continue
            if col.endswith("_years_since_birth") or col.endswith("_calendar_year"):
                continue

            if pd.api.types.is_datetime64_any_dtype(df[col]):
                date_cols.append(col)
            elif df[col].dtype == object:
                # Check if >50% of non-null values parse as dates
                non_null = df[col].dropna()
                if len(non_null) > 0:
                    parsed = pd.to_datetime(non_null, errors="coerce")
                    if parsed.notna().sum() / len(non_null) > 0.5:
                        df[col] = pd.to_datetime(df[col], errors="coerce")
                        date_cols.append(col)

        for col in date_cols:
            birth_series = df["record_id"].map(self._birth_dates)
            years_since = (df[col] - birth_series).dt.days / 365.25
            df[f"{col}_years_since_birth"] = years_since
            df[f"{col}_calendar_year"] = df[col].dt.year.astype("Int64")
            df = df.drop(columns=[col])

        return df

    def _load_cohort(self, con, id_map: dict):
        """Load the cohort table from output directory.

        The cohort file is already de-identified by CohortBuilder, so
        record_id values are not re-mapped here.
        """
        cohort_parquet = self.output_dir / "cohort.parquet"
        cohort_csv = self.output_dir / "cohort.csv"

        if cohort_parquet.exists():
            df = pd.read_parquet(cohort_parquet)
        elif cohort_csv.exists():
            df = pd.read_csv(cohort_csv)
        else:
            logger.warning("No cohort file found, skipping cohort table")
            return

        # Cohort is already de-identified by CohortBuilder — no re-mapping.

        # Keep only the standardized cohort columns (demographics + survival).
        # Source files often carry dozens of extra columns (addresses, MRNs,
        # names, etc.) that must not appear in the de-identified database.
        allowed = _COHORT_ALLOWED_COLUMNS & set(df.columns)
        dropped = set(df.columns) - allowed
        if dropped:
            logger.info("Cohort: keeping only standardized columns, dropping %d extras: %s",
                        len(dropped), sorted(dropped))
        df = df[[c for c in df.columns if c in allowed]]

        # Drop birth_date from the final cohort table — it was kept in the
        # parquet only so _load_birth_dates can use it for de-identifying
        # dates in extraction/harmonized tables.
        if "birth_date" in df.columns:
            df = df.drop(columns=["birth_date"])

        df = _strip_pii_columns(df, self._original_id_columns)
        df = filter_columns_by_non_missing(df, self.min_non_missing)

        con.execute("CREATE TABLE cohort AS SELECT * FROM df")
        logger.info("Loaded cohort table: %d rows, %d columns",
                     len(df), len(df.columns))

    def _load_extractions(self, con, id_map: dict):
        """Load extraction parquet into per-category tables."""
        extractions_dir = self.output_dir / "extractions"
        if not extractions_dir.exists():
            logger.warning("No extractions directory found, skipping")
            return

        extractions_file = extractions_dir / "extractions.parquet"
        if not extractions_file.exists():
            logger.warning("No extractions.parquet found, skipping")
            return

        df = pd.read_parquet(extractions_file)

        if "patient_id" in df.columns:
            df = df.rename(columns={"patient_id": "record_id"})

        # Rename configured patient ID columns to record_id
        df = self._rename_id_column(df)

        if "record_id" in df.columns:
            df = _deidentify_ids(df, "record_id", self.record_id_prefix, id_map)

        if self.deidentify_dates:
            df = self._deidentify_dates_df(df)

        df = _strip_pii_columns(df, self._original_id_columns)

        # Create per-category tables
        if "category" in df.columns:
            for category, group_df in df.groupby("category"):
                table_name = _table_name_from_category(str(category))

                if not self._is_table_approved(table_name):
                    logger.info("Skipping extraction category '%s' -> table '%s' (not in proposed_tables)",
                                category, table_name)
                    continue

                # Drop columns irrelevant to this category (all NaN)
                group_df = group_df.dropna(axis=1, how="all")
                # Drop the category column (redundant — the table name IS the category)
                if "category" in group_df.columns:
                    group_df = group_df.drop(columns=["category"])
                # Tag rows as AI-extracted
                group_df["data_source"] = "ai"
                # Apply same non-missing filter as cohort/harmonized tables
                group_df = filter_columns_by_non_missing(group_df, self.min_non_missing)

                if _table_exists(con, table_name):
                    _insert_aligned(con, table_name, group_df)
                else:
                    con.execute(
                        f'CREATE TABLE "{table_name}" AS SELECT * FROM group_df'
                    )
                logger.info("Loaded extraction category '%s' -> table '%s': %d rows, %d columns",
                            category, table_name, len(group_df), len(group_df.columns))

    def _load_harmonized(self, con, id_map: dict):
        """Load harmonized structured data into tables."""
        harmonized_dir = self.output_dir / "harmonized"
        if not harmonized_dir.exists():
            logger.warning("No harmonized directory found, skipping")
            return

        parquet_files = sorted(harmonized_dir.glob("*.parquet"))
        if not parquet_files:
            logger.warning("No harmonized parquet files found, skipping")
            return

        # Collect known categories from field_mappings config so we can
        # correctly parse multi-word category suffixes from filenames.
        known_categories = (
            list(self.config.field_mappings.keys())
            if self.config.field_mappings else []
        )

        for parquet_file in parquet_files:
            # Table name from file stem: files are named {source}_{category}.parquet
            stem = parquet_file.stem
            category = _category_from_harmonized_stem(stem, known_categories)
            table_name = _table_name_from_category(category)

            if not self._is_table_approved(table_name):
                logger.info("Skipping harmonized file '%s' -> table '%s' (not in proposed_tables)",
                            parquet_file.name, table_name)
                continue

            df = pd.read_parquet(parquet_file)

            # Rename configured patient ID columns to record_id
            df = self._rename_id_column(df)

            if "record_id" in df.columns:
                df = _deidentify_ids(
                    df, "record_id", self.record_id_prefix, id_map
                )

            if self.deidentify_dates:
                df = self._deidentify_dates_df(df)

            df = _strip_pii_columns(df, self._original_id_columns)

            # Tag rows as coming from structured data
            df["data_source"] = "structured_data"

            df = filter_columns_by_non_missing(df, self.min_non_missing)

            if _table_exists(con, table_name):
                _insert_aligned(con, table_name, df)
            else:
                con.execute(
                    f'CREATE TABLE "{table_name}" AS SELECT * FROM df'
                )
            logger.info("Loaded harmonized file '%s' -> table '%s': %d rows, %d columns",
                        parquet_file.name, table_name, len(df), len(df.columns))

    def _log_summary(self, con):
        """Log a summary of all tables."""
        tables = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()

        logger.info("Database summary:")
        for (table_name,) in tables:
            row_count = con.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()[0]
            col_count = con.execute(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name = ? AND table_schema = 'main'",
                [table_name],
            ).fetchone()[0]
            logger.info("  Table '%s': %d rows, %d columns",
                        table_name, row_count, col_count)
