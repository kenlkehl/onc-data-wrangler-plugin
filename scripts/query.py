#!/usr/bin/env python3
"""CLI wrapper for validated SQL queries against the project DuckDB database.

Loads config from active_config.yaml, validates SQL, executes against DuckDB,
applies privacy enforcement (cell suppression / audit logging), and prints
JSON to stdout.

Usage:
    uv run --directory ${CLAUDE_PLUGIN_ROOT} python scripts/query.py --sql "SELECT ..."
    uv run --directory ${CLAUDE_PLUGIN_ROOT} python scripts/query.py --sql "SELECT ..." --count-columns n_patients,n_cases
    uv run --directory ${CLAUDE_PLUGIN_ROOT} python scripts/query.py --sql "SELECT ..." --individual
    uv run --directory ${CLAUDE_PLUGIN_ROOT} python scripts/query.py --status
    uv run --directory ${CLAUDE_PLUGIN_ROOT} python scripts/query.py --privacy-mode
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add the plugin's src directory to the Python path
plugin_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(plugin_root / "src"))

import duckdb

from onc_wrangler.config import ProjectConfig, load_config
from onc_wrangler.query.privacy import log_query_audit, sanitize_query_output
from onc_wrangler.query.sql_validator import (
    identify_count_columns,
    validate_individual_sql,
    validate_sql,
)


def _resolve_config_path() -> str:
    explicit = os.environ.get("ONC_CONFIG_PATH", "").strip()
    if explicit:
        return explicit
    return str(Path.cwd() / "active_config.yaml")


def _load_config(config_path: str) -> ProjectConfig | None:
    if not config_path or not Path(config_path).exists():
        return None
    try:
        return load_config(config_path)
    except Exception:
        return None


def cmd_status(config: ProjectConfig | None, config_path: str) -> dict:
    if config is None:
        return {
            "status": "not_configured",
            "message": "No project configured. Run /onc-data-wrangler:make-database first.",
            "config_path_checked": config_path,
        }
    return {
        "status": "configured",
        "project_name": config.name,
        "db_path": str(config.db_path),
        "db_exists": config.db_path.exists(),
        "privacy_mode": getattr(config.query, "privacy_mode", "aggregate-only"),
    }


def cmd_privacy_mode(config: ProjectConfig | None) -> dict:
    if config is None:
        return {"error": "No project configured."}
    return {"privacy_mode": getattr(config.query, "privacy_mode", "aggregate-only")}


def cmd_execute_query(
    config: ProjectConfig, sql: str, count_columns: list[str] | None
) -> dict:
    db_path = config.db_path
    min_cell_size = config.query.min_cell_size
    max_query_rows = config.query.max_query_rows

    forbidden = (
        set(config.database.forbidden_output_columns)
        if config.database.forbidden_output_columns
        else {"record_id"}
    )
    validation = validate_sql(sql, forbidden)
    if not validation.valid:
        return {"error": "; ".join(validation.errors)}

    warnings = list(validation.warnings)

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(sql).fetchdf()
    except Exception as e:
        return {"error": f"Query execution error: {e}"}
    finally:
        con.close()

    if len(df) > max_query_rows:
        return {
            "error": (
                f"Query returned {len(df)} rows, exceeding the maximum "
                f"of {max_query_rows}. Add a LIMIT clause, use more "
                "specific filters, or increase aggregation granularity."
            )
        }

    if df.empty:
        return {
            "columns": list(df.columns),
            "rows": [],
            "n_rows": 0,
            "warnings": warnings,
            "suppression_applied": False,
        }

    detected_count_cols = identify_count_columns(list(df.columns), count_columns)
    df, suppression_applied = sanitize_query_output(df, detected_count_cols, min_cell_size)

    if suppression_applied:
        warnings.append(
            f"Counts < {min_cell_size} were suppressed in columns: "
            f"{detected_count_cols}"
        )

    df = df.where(df.notna(), None)

    return {
        "columns": list(df.columns),
        "rows": df.values.tolist(),
        "n_rows": len(df),
        "warnings": warnings,
        "suppression_applied": suppression_applied,
    }


def cmd_execute_individual_query(config: ProjectConfig, sql: str) -> dict:
    privacy_mode = getattr(config.query, "privacy_mode", "aggregate-only")
    if privacy_mode == "aggregate-only":
        return {
            "error": (
                "Individual-level queries are not allowed in aggregate-only "
                "privacy mode. Use aggregate queries instead."
            )
        }

    db_path = config.db_path
    max_query_rows = config.query.max_query_rows

    forbidden = (
        set(config.database.forbidden_output_columns)
        if config.database.forbidden_output_columns
        else {"record_id"}
    )
    validation = validate_individual_sql(sql, forbidden)
    if not validation.valid:
        return {"error": "; ".join(validation.errors)}

    warnings = list(validation.warnings)

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(sql).fetchdf()
    except Exception as e:
        return {"error": f"Query execution error: {e}"}
    finally:
        con.close()

    if len(df) > max_query_rows:
        return {
            "error": (
                f"Query returned {len(df)} rows, exceeding the maximum "
                f"of {max_query_rows}. Add a LIMIT clause or use more "
                "specific filters."
            )
        }

    if df.empty:
        return {
            "columns": list(df.columns),
            "rows": [],
            "n_rows": 0,
            "warnings": warnings,
            "suppression_applied": False,
        }

    if privacy_mode == "individual-with-audit":
        try:
            log_query_audit(str(config.output_dir), sql, len(df), df)
        except Exception as e:
            warnings.append(f"Audit logging failed: {e}")

    df = df.where(df.notna(), None)

    return {
        "columns": list(df.columns),
        "rows": df.values.tolist(),
        "n_rows": len(df),
        "warnings": warnings,
        "suppression_applied": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Query the project DuckDB database with privacy enforcement.")
    parser.add_argument("--sql", help="SQL query to execute")
    parser.add_argument("--count-columns", help="Comma-separated list of count column names for suppression")
    parser.add_argument("--individual", action="store_true", help="Execute as individual-level query (no aggregation required)")
    parser.add_argument("--status", action="store_true", help="Print server status and exit")
    parser.add_argument("--privacy-mode", action="store_true", help="Print privacy mode and exit")
    args = parser.parse_args()

    config_path = _resolve_config_path()
    config = _load_config(config_path)

    if args.status:
        print(json.dumps(cmd_status(config, config_path), indent=2, default=str))
        return

    if args.privacy_mode:
        print(json.dumps(cmd_privacy_mode(config), indent=2))
        return

    if not args.sql:
        parser.error("--sql is required unless using --status or --privacy-mode")

    if config is None:
        print(json.dumps({"error": "No project configured. Run /onc-data-wrangler:make-database first."}, indent=2))
        sys.exit(1)

    count_cols = [c.strip() for c in args.count_columns.split(",")] if args.count_columns else None

    if args.individual:
        result = cmd_execute_individual_query(config, args.sql)
    else:
        result = cmd_execute_query(config, args.sql, count_cols)

    print(json.dumps(result, indent=2, default=str))
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
