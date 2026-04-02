"""Cohort builder from structured tables.

Generalized cohort definition: user specifies which columns contain
patient IDs, diagnosis codes, dates, and demographics. Produces a
standardized cohort DataFrame.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class CohortConfig:
    """Configuration for cohort construction."""
    patient_id_column: str = "record_id"
    birth_date_column: Optional[str] = None
    death_date_column: Optional[str] = None
    death_indicator_column: Optional[str] = None
    sex_column: Optional[str] = None
    race_column: Optional[str] = None
    ethnicity_column: Optional[str] = None
    diagnosis_code_column: Optional[str] = None
    diagnosis_code_filter: list = field(default_factory=list)
    followup_date: str = "2025-07-01"
    id_prefix: str = "patient"


class CohortBuilder:
    """Build a standardized cohort from source data.

    Produces a cohort DataFrame with standardized columns:
    - record_id: De-identified patient identifier
    - sex, race, ethnicity: Demographics
    - birth_to_last_followup_or_death_years: Time-to-event
    - died_yes_or_no: Vital status indicator
    """

    def __init__(self, config: Optional[CohortConfig] = None):
        self.config = config or CohortConfig()
        self.original_ids = None

    def build_from_dataframes(
        self,
        patient_df: pd.DataFrame,
        diagnosis_df: Optional[pd.DataFrame] = None,
        demographics_df: Optional[pd.DataFrame] = None,
        demographics_dfs: Optional[list[pd.DataFrame]] = None,
    ) -> pd.DataFrame:
        """Build cohort from one or more source DataFrames.

        Args:
            patient_df: Primary patient table with IDs and optionally demographics.
            diagnosis_df: Optional diagnosis table for filtering.
            demographics_df: Optional single demographics table (legacy).
            demographics_dfs: Optional list of demographics tables to merge.
                Each is left-joined in order; later files fill in missing
                values without overwriting earlier ones.

        Returns:
            Standardized cohort DataFrame.
        """
        cfg = self.config
        pid = cfg.patient_id_column

        # Start with unique patient IDs
        cohort = patient_df[[pid]].drop_duplicates().copy()

        # Filter by diagnosis codes if configured
        if diagnosis_df is not None and cfg.diagnosis_code_column and cfg.diagnosis_code_filter:
            pattern = "|".join(cfg.diagnosis_code_filter)
            mask = diagnosis_df[cfg.diagnosis_code_column].str.contains(pattern, na=False)
            filtered_ids = diagnosis_df.loc[mask, pid].unique()
            cohort = cohort[cohort[pid].isin(filtered_ids)]
            logger.info("Cohort size after filtering: %d patients", len(cohort))

        # Merge demographics from multiple tables if provided
        all_demo_dfs = list(demographics_dfs or [])
        if demographics_df is not None and not all_demo_dfs:
            # Legacy single-file path
            all_demo_dfs = [demographics_df]

        for i, demo_df in enumerate(all_demo_dfs):
            new_cols = [c for c in demo_df.columns if c != pid and c not in cohort.columns]
            if new_cols:
                # Columns not yet in cohort — simple left join
                cohort = cohort.merge(demo_df[[pid] + new_cols].drop_duplicates(subset=[pid]), on=pid, how="left")
                logger.info("Merged %d new columns from demographics source %d", len(new_cols), i + 1)
            # For columns already in cohort, fill missing values from this source
            overlap_cols = [c for c in demo_df.columns if c != pid and c in cohort.columns]
            if overlap_cols:
                temp = demo_df[[pid] + overlap_cols].drop_duplicates(subset=[pid])
                cohort = cohort.merge(temp, on=pid, how="left", suffixes=("", "_fill"))
                for col in overlap_cols:
                    fill_col = col + "_fill"
                    if fill_col in cohort.columns:
                        cohort[col] = cohort[col].fillna(cohort[fill_col])
                        cohort = cohort.drop(columns=[fill_col])
                logger.info("Filled %d overlapping columns from demographics source %d", len(overlap_cols), i + 1)

        # Merge demographic columns from patient table
        demo_cols = []
        for col_attr in ("sex_column", "race_column", "ethnicity_column", "birth_date_column", "death_date_column", "death_indicator_column"):
            col = getattr(cfg, col_attr)
            if col and col in patient_df.columns:
                demo_cols.append(col)
        if demo_cols:
            cohort = cohort.merge(patient_df[[pid] + demo_cols].drop_duplicates(subset=[pid]), on=pid, how="left")

        # Standardize column names
        cohort = self._standardize_columns(cohort)

        # Store original IDs before de-identification
        self.original_ids = cohort["record_id"].tolist()

        # Compute survival times
        cohort = self._compute_survival_times(cohort)

        # De-identify
        cohort = self._deidentify(cohort)

        return cohort.reset_index(drop=True)

    def build_from_files(
        self,
        patient_file: str,
        diagnosis_file: Optional[str] = None,
        demographics_file: Optional[str] = None,
        demographics_files: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """Build cohort from CSV/parquet files."""
        patient_df = _read_file(patient_file)
        diagnosis_df = _read_file(diagnosis_file) if diagnosis_file else None
        demographics_dfs = None
        if demographics_files:
            demographics_dfs = [_read_file(f) for f in demographics_files]
        elif demographics_file:
            demographics_dfs = [_read_file(demographics_file)]
        return self.build_from_dataframes(patient_df, diagnosis_df, demographics_dfs=demographics_dfs)

    def _standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rename source columns to standardized names."""
        cfg = self.config
        renames = {}
        renames[cfg.patient_id_column] = "record_id"
        if cfg.sex_column and cfg.sex_column in df.columns:
            renames[cfg.sex_column] = "sex"
        if cfg.race_column and cfg.race_column in df.columns:
            renames[cfg.race_column] = "race"
        if cfg.ethnicity_column and cfg.ethnicity_column in df.columns:
            renames[cfg.ethnicity_column] = "ethnicity"
        if cfg.birth_date_column and cfg.birth_date_column in df.columns:
            renames[cfg.birth_date_column] = "birth_date"
        if cfg.death_date_column and cfg.death_date_column in df.columns:
            renames[cfg.death_date_column] = "death_date"
        if cfg.death_indicator_column and cfg.death_indicator_column in df.columns:
            renames[cfg.death_indicator_column] = "died_yes_or_no"
        return df.rename(columns=renames)

    def _compute_survival_times(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute time-to-event fields from dates."""
        if "birth_date" not in df.columns:
            return df

        df["birth_date"] = pd.to_datetime(df["birth_date"], errors="coerce")
        followup_date = pd.to_datetime(self.config.followup_date)

        if "death_date" in df.columns:
            df["death_date"] = pd.to_datetime(df["death_date"], errors="coerce")
            last_date = df["death_date"].fillna(followup_date)
        else:
            last_date = followup_date

        df["birth_to_last_followup_or_death_years"] = (last_date - df["birth_date"]) / pd.Timedelta(days=365.25)

        if "death_date" in df.columns:
            df["birth_to_death_years"] = (df["death_date"] - df["birth_date"]) / pd.Timedelta(days=365.25)
            df = df.drop(columns=["death_date"])

        # Keep birth_date in the output -- the DatabaseBuilder needs it for
        # date de-identification of extraction tables (converting raw dates to
        # *_years_since_birth).  The database builder's _deidentify_dates_df
        # will drop birth_date from the final DuckDB cohort table.

        return df

    def _deidentify(self, df: pd.DataFrame) -> pd.DataFrame:
        """Replace raw IDs with sequential de-identified IDs."""
        prefix = self.config.id_prefix
        unique_ids = sorted(df["record_id"].unique(), key=str)
        id_map = {old_id: f"{prefix}_{i:06d}" for i, old_id in enumerate(unique_ids, start=1)}
        df = df.copy()
        df["record_id"] = df["record_id"].map(id_map)
        return df


def _read_file(path: str) -> pd.DataFrame:
    """Read a CSV or parquet file."""
    path = Path(path)
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, low_memory=False)
