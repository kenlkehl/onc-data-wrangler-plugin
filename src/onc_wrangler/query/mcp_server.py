"""FastMCP server for executing validated SQL queries against the project database."""
import logging
from pathlib import Path

import duckdb
from mcp.server.fastmcp import FastMCP

from ..config import ProjectConfig
from .sql_validator import validate_sql, validate_individual_sql, identify_count_columns
from .privacy import sanitize_query_output, log_query_audit

logger = logging.getLogger(__name__)


def create_server_from_config(config: ProjectConfig) -> FastMCP:
    """Create a FastMCP server from project configuration.

    Args:
        config: ProjectConfig with query settings.

    Returns:
        Configured FastMCP instance.
    """
    query_config = config.query
    db_path = config.db_path
    schema_path = config.schema_path
    summary_path = config.summary_path

    min_cell_size = query_config.min_cell_size
    max_query_rows = query_config.max_query_rows

    # Read privacy mode from config (default: "aggregate-only")
    privacy_mode = getattr(query_config, "privacy_mode", "aggregate-only")

    server_instructions = (
        f"You are a clinical dataset analysis assistant for the {config.name} project. "
        "Use the execute_query tool to run validated SQL queries against the database. "
        "Use the schema and summary resources to understand the database structure."
    )

    mcp = FastMCP(
        name=f"{config.name} Analysis Server",
        instructions=server_instructions,
        host=query_config.mcp_host,
        port=query_config.mcp_port,
    )

    # --- MCP Resources ---

    @mcp.resource(f"{config.name}://schema")
    def get_schema() -> str:
        """Database schema: table names, columns, and types."""
        if schema_path.exists():
            return schema_path.read_text()
        return "Schema file not yet generated. Run the metadata pipeline stage first."

    @mcp.resource(f"{config.name}://summary")
    def get_summary() -> str:
        """Pre-computed summary statistics for the dataset."""
        if summary_path.exists():
            return summary_path.read_text()
        return "Summary file not yet generated. Run the metadata pipeline stage first."

    # --- MCP Tools ---

    @mcp.tool()
    def execute_query(
        sql: str,
        count_columns: list[str] | None = None,
    ) -> dict:
        """Execute a validated SQL query against the database.

        The query must be a single SELECT statement with aggregation (GROUP BY or
        aggregate functions like COUNT, SUM, AVG). No SELECT *, no record_id in
        output columns. record_id may be used in JOINs, WHERE, and CTEs.

        IMPORTANT: Some tables have multiple rows per patient (e.g., diagnosis,
        treatment, biomarker). When computing patient-level statistics like
        prevalence or percentages, use COUNT(DISTINCT record_id) for the
        denominator, not COUNT(*). Check the schema resource for which tables
        have multiple rows per patient.

        Args:
            sql: A SQL SELECT query with aggregation.
            count_columns: Optional explicit list of output column names that
                contain counts (for privacy suppression).

        Returns:
            Dict with keys: columns, rows, n_rows, warnings, suppression_applied.
            Or dict with key: error.
        """
        # 1. Validate SQL
        forbidden = set(config.database.forbidden_output_columns) if config.database.forbidden_output_columns else {"record_id"}
        validation = validate_sql(sql, forbidden)
        if not validation.valid:
            return {"error": "; ".join(validation.errors)}

        warnings = list(validation.warnings)

        # 2. Execute query
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            df = con.execute(sql).fetchdf()
        except Exception as e:
            return {"error": f"Query execution error: {e}"}
        finally:
            con.close()

        # 3. Row limit check
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

        # 4. Identify count columns and apply suppression
        detected_count_cols = identify_count_columns(
            list(df.columns), count_columns
        )
        df, suppression_applied = sanitize_query_output(
            df, detected_count_cols, min_cell_size
        )

        if suppression_applied:
            warnings.append(
                f"Counts < {min_cell_size} were suppressed in columns: "
                f"{detected_count_cols}"
            )

        # 5. Convert to serializable format
        df = df.where(df.notna(), None)

        return {
            "columns": list(df.columns),
            "rows": df.values.tolist(),
            "n_rows": len(df),
            "warnings": warnings,
            "suppression_applied": suppression_applied,
        }

    # --- Privacy mode tool ---

    @mcp.tool()
    def get_privacy_mode() -> dict:
        """Return the current privacy mode for the query server.

        Returns:
            Dict with key 'privacy_mode' set to one of:
            "aggregate-only", "individual", or "individual-with-audit".
        """
        return {"privacy_mode": privacy_mode}

    # --- Individual query tool (registered when privacy_mode allows it) ---

    if privacy_mode != "aggregate-only":

        @mcp.tool()
        def execute_individual_query(
            sql: str,
        ) -> dict:
            """Execute a validated individual-level SQL query against the database.

            Unlike execute_query, this tool does NOT require aggregation.
            It still enforces: single SELECT statement, no SELECT *, no
            forbidden columns in output, and max_query_rows.
            Cell suppression is NOT applied.

            Only available when privacy_mode is not "aggregate-only".

            Args:
                sql: A SQL SELECT query (aggregation not required).

            Returns:
                Dict with keys: columns, rows, n_rows, warnings, suppression_applied.
                Or dict with key: error.
            """
            # 1. Validate SQL (individual-level: no aggregation requirement)
            forbidden = set(config.database.forbidden_output_columns) if config.database.forbidden_output_columns else {"record_id"}
            validation = validate_individual_sql(sql, forbidden)
            if not validation.valid:
                return {"error": "; ".join(validation.errors)}

            warnings = list(validation.warnings)

            # 2. Execute query
            con = duckdb.connect(str(db_path), read_only=True)
            try:
                df = con.execute(sql).fetchdf()
            except Exception as e:
                return {"error": f"Query execution error: {e}"}
            finally:
                con.close()

            # 3. Row limit check
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

            # 4. Audit logging when in "individual-with-audit" mode
            if privacy_mode == "individual-with-audit":
                try:
                    log_query_audit(
                        str(config.output_dir),
                        sql,
                        len(df),
                        df,
                    )
                except Exception as e:
                    logger.warning("Failed to write audit log: %s", e)
                    warnings.append(f"Audit logging failed: {e}")

            # 5. Convert to serializable format (no cell suppression)
            df = df.where(df.notna(), None)

            return {
                "columns": list(df.columns),
                "rows": df.values.tolist(),
                "n_rows": len(df),
                "warnings": warnings,
                "suppression_applied": False,
            }

    return mcp
