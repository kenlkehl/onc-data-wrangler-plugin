"""Generate schema and summary statistics metadata from a DuckDB database.

Produces markdown files describing table structures and aggregate statistics
for use as LLM context.
"""

import logging
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)


def get_tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Get all table names in the database."""
    result = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' ORDER BY table_name"
    ).fetchall()
    return [r[0] for r in result]


def get_columns(
    con, table: str, forbidden_columns: set = None
) -> pd.DataFrame:
    """Get column info for a table, excluding forbidden columns."""
    df = con.execute(
        "SELECT column_name, data_type, is_nullable "
        "FROM information_schema.columns "
        "WHERE table_name = ? AND table_schema = 'main' "
        "ORDER BY ordinal_position",
        [table],
    ).fetchdf()
    if forbidden_columns:
        df = df[~df["column_name"].isin(forbidden_columns)]
    return df


def get_row_count(con, table: str) -> int:
    """Get row count for a table."""
    result = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
    return result[0]


def suppress_count(count: int, min_cell_size: int) -> str:
    """Replace small counts with suppression marker."""
    if count < min_cell_size:
        return f"<{min_cell_size}"
    return str(count)


def _count_distinct_patients(con, table: str) -> int | None:
    """Count distinct patients in a table, if a patient ID column exists.

    Returns None if no patient ID column is found.
    """
    col_df = con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = ? AND table_schema = 'main'",
        [table],
    ).fetchdf()
    col_names = set(col_df["column_name"].tolist())
    for id_col in ("record_id", "patient_id"):
        if id_col in col_names:
            result = con.execute(
                f'SELECT COUNT(DISTINCT "{id_col}") FROM "{table}"'
            ).fetchone()
            return result[0]
    return None


def generate_schema(
    con,
    project_name: str = "Dataset",
    forbidden_columns: set = None,
) -> str:
    """Generate schema markdown describing all tables."""
    tables = get_tables(con)
    lines = []
    lines.append(f"# {project_name} Schema")
    lines.append("")

    for table in tables:
        row_count = get_row_count(con, table)
        columns = get_columns(con, table, forbidden_columns)
        n_patients = _count_distinct_patients(con, table)

        lines.append(f"## Table: `{table}`")
        lines.append("")
        lines.append(f"- **Rows**: {row_count}")
        if n_patients is not None and n_patients != row_count:
            lines.append(
                f"- **Unique patients**: {n_patients} "
                f"(multiple rows per patient; use COUNT(DISTINCT record_id) "
                f"for patient-level denominators)"
            )
        lines.append(f"- **Columns**: {len(columns)}")
        lines.append("")
        lines.append("| Column | Type | Nullable |")
        lines.append("|--------|------|----------|")

        for _, row in columns.iterrows():
            col_name = row["column_name"]
            data_type = row["data_type"]
            nullable = row["is_nullable"]
            lines.append(f"| `{col_name}` | {data_type} | {nullable} |")

        lines.append("")

    return "\n".join(lines)


def generate_summary(
    con,
    project_name: str = "Dataset",
    forbidden_columns: set = None,
    min_cell_size: int = 10,
) -> str:
    """Generate summary statistics markdown with cell suppression."""
    tables = get_tables(con)
    lines = []
    lines.append(f"# {project_name} Summary Statistics")
    lines.append("")

    for table in tables:
        row_count = get_row_count(con, table)
        columns = get_columns(con, table, forbidden_columns)

        lines.append(f"## Table: `{table}` ({row_count} rows)")
        lines.append("")

        for _, row in columns.iterrows():
            col_name = row["column_name"]
            data_type = row["data_type"]

            if data_type == "VARCHAR":
                _summarize_categorical(
                    con, table, col_name, min_cell_size, lines
                )
            elif data_type in ("DOUBLE", "BIGINT", "INTEGER", "FLOAT"):
                _summarize_numeric(con, table, col_name, lines)

        lines.append("")

    return "\n".join(lines)


_SKIP_COLUMN_PATTERNS = {
    "date", "time", "timestamp", "calendar_year", "years_since_birth",
    "record_id", "patient_id", "id", "data_source",
}


def _is_dashboard_column(col_name: str) -> bool:
    """Return True if a column is suitable for the summary dashboard.

    Filters out date/time columns, ID columns, and interval-since-birth
    columns that aren't useful for aggregate summaries.
    """
    lower = col_name.lower()
    for pattern in _SKIP_COLUMN_PATTERNS:
        if pattern in lower:
            return False
    return True


def generate_summary_stats(
    con,
    project_name: str = "Dataset",
    forbidden_columns: set = None,
    min_cell_size: int = 10,
) -> dict:
    """Generate structured summary statistics as a dict for JSON serialization.

    Returns a dict with project overview, table metadata, demographics
    (from the cohort table if present), and per-table key categorical fields.
    Mirrors the pan-top chatbot strategy: demographics grid, table list,
    and a small number of key categorical fields per table.
    """
    tables = get_tables(con)

    # Build table list with row/column counts and column names
    table_list = []
    for table in tables:
        row_count = get_row_count(con, table)
        columns = get_columns(con, table, forbidden_columns)
        n_patients = _count_distinct_patients(con, table)
        entry = {
            "name": table,
            "row_count": row_count,
            "column_count": len(columns),
            "column_names": columns["column_name"].tolist(),
        }
        if n_patients is not None:
            entry["unique_patients"] = n_patients
            if n_patients != row_count:
                entry["note"] = (
                    "Multiple rows per patient. Use COUNT(DISTINCT record_id) "
                    "for patient-level denominators, not COUNT(*)."
                )
        table_list.append(entry)

    # Total patients from cohort table (if it exists)
    total_patients = None
    if "cohort" in tables:
        total_patients = get_row_count(con, "cohort")

    # Demographics from cohort table
    demographics = {}
    if "cohort" in tables:
        cohort_cols = get_columns(con, "cohort", forbidden_columns)
        col_names = set(cohort_cols["column_name"].tolist())
        for demo_col in ("sex", "race", "ethnicity"):
            if demo_col in col_names:
                demographics[demo_col] = _get_categorical_values(
                    con, "cohort", demo_col, min_cell_size
                )

    # Per-table key categorical summaries (limited, filtered)
    table_summaries = {}
    for table in tables:
        columns = get_columns(con, table, forbidden_columns)
        cat_summaries = []

        for _, row in columns.iterrows():
            col_name = row["column_name"]
            data_type = row["data_type"]

            if not _is_dashboard_column(col_name):
                continue

            if data_type == "VARCHAR":
                values = _get_categorical_values(
                    con, table, col_name, min_cell_size
                )
                if values:
                    cat_summaries.append({
                        "column": col_name,
                        "values": values,
                    })

        # Keep only the first few key fields per table
        if cat_summaries:
            table_summaries[table] = {
                "categorical": cat_summaries[:4],
            }

    return {
        "project_name": project_name,
        "total_patients": total_patients,
        "tables": table_list,
        "demographics": demographics,
        "table_summaries": table_summaries,
    }


def _get_categorical_values(
    con, table: str, col_name: str, min_cell_size: int
) -> list[dict]:
    """Get top categorical values with suppressed counts."""
    result = con.execute(
        f'SELECT "{col_name}" AS value, COUNT(*) AS count '
        f'FROM "{table}" '
        f'WHERE "{col_name}" IS NOT NULL '
        f'GROUP BY "{col_name}" '
        f"ORDER BY count DESC "
        f"LIMIT 15"
    ).fetchdf()

    if result.empty:
        return []

    values = []
    for _, row in result.iterrows():
        count = int(row["count"])
        values.append({
            "label": str(row["value"]),
            "n": count if count >= min_cell_size else None,
            "suppressed": count < min_cell_size,
        })
    return values


def _get_numeric_stats(con, table: str, col_name: str) -> dict | None:
    """Get numeric column statistics."""
    result = con.execute(
        f"SELECT "
        f'COUNT("{col_name}") AS count, '
        f'MIN("{col_name}") AS min, '
        f'MAX("{col_name}") AS max, '
        f'AVG("{col_name}") AS avg, '
        f'MEDIAN("{col_name}") AS median '
        f'FROM "{table}" '
        f'WHERE "{col_name}" IS NOT NULL'
    ).fetchone()

    if result is None or result[0] == 0:
        return None

    count, min_val, max_val, avg_val, median_val = result
    return {
        "count": count,
        "min": round(float(min_val), 2),
        "max": round(float(max_val), 2),
        "mean": round(float(avg_val), 2),
        "median": round(float(median_val), 2),
    }


def _summarize_categorical(
    con, table: str, col_name: str, min_cell_size: int, lines: list
):
    """Add categorical column summary to lines."""
    lines.append(f"### `{col_name}` (categorical)")
    lines.append("")

    result = con.execute(
        f'SELECT "{col_name}" AS value, COUNT(*) AS count '
        f'FROM "{table}" '
        f'WHERE "{col_name}" IS NOT NULL '
        f'GROUP BY "{col_name}" '
        f"ORDER BY count DESC "
        f"LIMIT 15"
    ).fetchdf()

    if result.empty:
        lines.append("No non-null values.")
        lines.append("")
        return

    lines.append("| Value | Count |")
    lines.append("|-------|-------|")

    for _, row in result.iterrows():
        value = row["value"]
        count = int(row["count"])
        count_str = suppress_count(count, min_cell_size)
        lines.append(f"| {value} | {count_str} |")

    lines.append("")


def _summarize_numeric(con, table: str, col_name: str, lines: list):
    """Add numeric column summary to lines."""
    lines.append(f"### `{col_name}` (numeric)")
    lines.append("")

    result = con.execute(
        f"SELECT "
        f'COUNT("{col_name}") AS count, '
        f'MIN("{col_name}") AS min, '
        f'MAX("{col_name}") AS max, '
        f'AVG("{col_name}") AS avg, '
        f'MEDIAN("{col_name}") AS median, '
        f"PERCENTILE_CONT({0.25}) WITHIN GROUP "
        f'(ORDER BY "{col_name}") AS q1, '
        f"PERCENTILE_CONT({0.75}) WITHIN GROUP "
        f'(ORDER BY "{col_name}") AS q3 '
        f'FROM "{table}" '
        f'WHERE "{col_name}" IS NOT NULL'
    ).fetchone()

    count, min_val, max_val, avg_val, median_val, q1_val, q3_val = result

    lines.append(f"- **Count**: {count}")
    lines.append(f"- **Min**: {min_val:.2f}")
    lines.append(f"- **Max**: {max_val:.2f}")
    lines.append(f"- **Mean**: {avg_val:.2f}")
    lines.append(f"- **Median**: {median_val:.2f}")
    lines.append(f"- **Q1 (25%)**: {q1_val:.2f}")
    lines.append(f"- **Q3 (75%)**: {q3_val:.2f}")
    lines.append("")
