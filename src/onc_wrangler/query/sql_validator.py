"""Pre-execution SQL validation using sqlglot AST parsing."""
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

_AGGREGATE_FUNCTIONS = frozenset({
    'count', 'sum', 'avg', 'min', 'max', 'median', 'mode',
    'stddev', 'stddev_pop', 'stddev_samp', 'variance', 'var_pop', 'var_samp',
    'list', 'list_agg', 'string_agg', 'group_concat', 'array_agg',
    'first', 'last', 'any_value', 'arbitrary',
    'arg_min', 'arg_max', 'argmin', 'argmax',
    'bool_and', 'bool_or', 'every',
    'bit_and', 'bit_or', 'bit_xor',
    'corr', 'covar_pop', 'covar_samp',
    'regr_slope', 'regr_intercept', 'regr_count', 'regr_r2',
    'regr_avgx', 'regr_avgy', 'regr_sxx', 'regr_syy', 'regr_sxy',
    'approx_count_distinct', 'approx_quantile',
    'quantile_cont', 'quantile_disc', 'percentile_cont', 'percentile_disc',
    'histogram', 'entropy', 'kurtosis', 'skewness', 'freq', 'frequency',
})


@dataclass
class ValidationResult:
    """Result of SQL validation."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_sql(sql: str, forbidden_output_columns: set = None) -> ValidationResult:
    """Validate a SQL string for safety and privacy compliance.

    Checks:
    1. Single statement only (no ;-separated batches)
    2. Must be a SELECT (reject DDL/DML)
    3. No SELECT * (must enumerate columns)
    4. Forbidden columns must not appear in outermost SELECT expressions
    5. Must contain aggregation (aggregate function or GROUP BY)
    6. Warns (but allows) window functions
    """
    if forbidden_output_columns is None:
        forbidden_output_columns = {"record_id"}

    sql = sql.strip().rstrip(";")
    if not sql:
        return ValidationResult(valid=False, errors=["Empty SQL statement."])

    errors = []
    warnings = []

    try:
        statements = sqlglot.parse(sql, dialect="duckdb")
    except sqlglot.errors.ParseError as e:
        return ValidationResult(valid=False, errors=[f"SQL parse error: {e}"])

    # Filter out None statements
    statements = [s for s in statements if s is not None]

    if len(statements) > 1:
        errors.append(f"Only a single SQL statement is allowed. Found {len(statements)} statements.")
        return ValidationResult(valid=False, errors=errors)

    stmt = statements[0]

    # Check it's a SELECT (or UNION/INTERSECT/EXCEPT of SELECTs)
    if not isinstance(stmt, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        errors.append(f"Only SELECT statements are allowed. Got: {type(stmt).__name__}.")
        return ValidationResult(valid=False, errors=errors)

    # No SELECT *
    if _has_select_star(stmt):
        errors.append("SELECT * is not allowed. Please enumerate the columns you need.")

    # Check forbidden columns in outermost SELECT
    forbidden = _find_forbidden_columns_in_select(stmt, forbidden_output_columns)
    if forbidden:
        col_list = ", ".join(sorted(set(forbidden)))
        errors.append(f"{col_list} must not appear in the outermost SELECT list. These columns may be used in JOINs, WHERE, and CTEs, but not in output columns.")

    # Must have aggregation
    if not _has_aggregation(stmt):
        errors.append("Query must contain at least one aggregate function (COUNT, SUM, AVG, etc.) or a GROUP BY clause. Raw row-level queries are not allowed.")

    # Warn about window functions
    if _has_window_functions(stmt):
        warnings.append("Query contains window functions. Results are allowed but ensure they do not produce patient-level output.")

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)


def validate_individual_sql(sql: str, forbidden_output_columns: set = None) -> ValidationResult:
    """Validate a SQL string for individual-level (non-aggregate) queries.

    Like validate_sql but does NOT require aggregation.  Still enforces:
    1. Single statement only (no ;-separated batches)
    2. Must be a SELECT (reject DDL/DML)
    3. No SELECT * (must enumerate columns)
    4. Forbidden columns must not appear in outermost SELECT expressions

    Additionally warns (not error) if the query lacks a LIMIT clause.
    """
    if forbidden_output_columns is None:
        forbidden_output_columns = {"record_id"}

    sql = sql.strip().rstrip(";")
    if not sql:
        return ValidationResult(valid=False, errors=["Empty SQL statement."])

    errors = []
    warnings = []

    try:
        statements = sqlglot.parse(sql, dialect="duckdb")
    except sqlglot.errors.ParseError as e:
        return ValidationResult(valid=False, errors=[f"SQL parse error: {e}"])

    # Filter out None statements
    statements = [s for s in statements if s is not None]

    if len(statements) > 1:
        errors.append(f"Only a single SQL statement is allowed. Found {len(statements)} statements.")
        return ValidationResult(valid=False, errors=errors)

    stmt = statements[0]

    # Check it's a SELECT (or UNION/INTERSECT/EXCEPT of SELECTs)
    if not isinstance(stmt, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        errors.append(f"Only SELECT statements are allowed. Got: {type(stmt).__name__}.")
        return ValidationResult(valid=False, errors=errors)

    # No SELECT *
    if _has_select_star(stmt):
        errors.append("SELECT * is not allowed. Please enumerate the columns you need.")

    # Check forbidden columns in outermost SELECT
    forbidden = _find_forbidden_columns_in_select(stmt, forbidden_output_columns)
    if forbidden:
        col_list = ", ".join(sorted(set(forbidden)))
        errors.append(f"{col_list} must not appear in the outermost SELECT list. These columns may be used in JOINs, WHERE, and CTEs, but not in output columns.")

    # Warn if no LIMIT clause (not an error)
    if not _has_limit(stmt):
        warnings.append("Query does not have a LIMIT clause. Consider adding one to avoid returning too many rows.")

    # Warn about window functions
    if _has_window_functions(stmt):
        warnings.append("Query contains window functions. Results are allowed but ensure they do not produce patient-level output.")

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)


def identify_count_columns(column_names: list[str], explicit_count_cols: list[str] = None) -> list[str]:
    """Detect which output columns contain counts needing suppression."""
    if explicit_count_cols:
        return [c.lower().strip() for c in explicit_count_cols]

    _false_positives = frozenset({'n_stage', 'm_stage', 't_stage', 'total_dose', 'total_fractions', 'n_category'})
    count_cols = []
    for col in column_names:
        col_lower = col.lower().strip()
        if col_lower in _false_positives:
            continue
        if _is_count_column_name(col_lower):
            count_cols.append(col)
    return count_cols


def _is_count_column_name(name: str) -> bool:
    """Check if a column name looks like a count column."""
    exact = frozenset({'count', 'cnt', 'n', 'total', 'freq', 'frequency'})
    if name in exact:
        return True
    if name.startswith(('n_', 'num_', 'count_', 'cnt_')):
        return True
    if name.endswith(('_count', '_cnt', '_total', '_n', '_freq')):
        return True
    domain_patterns = frozenset({'n_patients', 'n_cases', 'n_tested', 'n_positive', 'n_events', 'n_treated', 'n_censored'})
    if name in domain_patterns:
        return True
    return False


def _has_select_star(stmt) -> bool:
    """Check if the outermost SELECT(s) contain SELECT *."""
    for select in _get_outermost_selects(stmt):
        for expr in select.expressions:
            if isinstance(expr, exp.Star):
                return True
            if isinstance(expr, exp.Column) and isinstance(expr.this, exp.Star):
                return True
    return False


def _find_forbidden_columns_in_select(stmt, forbidden_names: set) -> list:
    """Check outermost SELECT expressions for forbidden columns."""
    forbidden = []
    for select in _get_outermost_selects(stmt):
        for expr in select.expressions:
            for col in expr.find_all(exp.Column):
                if _is_in_subquery(col, select):
                    continue
                col_name = col.name.lower()
                if col_name in forbidden_names:
                    # Check if it's inside an aggregate function
                    parent = col.parent
                    in_agg = False
                    while parent is not None and parent is not select:
                        if isinstance(parent, exp.AggFunc):
                            in_agg = True
                            break
                        if isinstance(parent, exp.Anonymous):
                            func_name = parent.name.lower() if parent.name else ""
                            if func_name in _AGGREGATE_FUNCTIONS:
                                in_agg = True
                                break
                        parent = parent.parent
                    if not in_agg:
                        forbidden.append(col_name)
    return forbidden


def _has_aggregation(stmt) -> bool:
    """Check if the statement contains aggregate functions or GROUP BY."""
    for select in _get_all_selects(stmt):
        if select.args.get("group"):
            return True
        for node in select.walk():
            if isinstance(node, exp.AggFunc):
                return True
            if isinstance(node, exp.Anonymous):
                func_name = node.name.lower() if node.name else ""
                if func_name in _AGGREGATE_FUNCTIONS:
                    return True
    return False


def _has_limit(stmt) -> bool:
    """Check if the outermost statement has a LIMIT clause."""
    # For UNION/INTERSECT/EXCEPT, check the top-level node
    if hasattr(stmt, 'args') and stmt.args.get("limit"):
        return True
    # For a plain SELECT, check its limit arg
    for select in _get_outermost_selects(stmt):
        if select.args.get("limit"):
            return True
    return False


def _has_window_functions(stmt) -> bool:
    """Check if the statement contains window functions."""
    for node in stmt.walk():
        if isinstance(node, exp.Window):
            return True
    return False


def _get_outermost_selects(stmt) -> list:
    """Get the outermost SELECT statements."""
    if isinstance(stmt, (exp.Union, exp.Intersect, exp.Except)):
        selects = []
        for side in [stmt.left, stmt.right]:
            selects.extend(_get_outermost_selects(side))
        return selects
    if isinstance(stmt, exp.Select):
        return [stmt]
    return []


def _get_all_selects(stmt) -> list:
    """Get all SELECT nodes in the statement."""
    return list(stmt.find_all(exp.Select))


def _is_in_subquery(node, outer_select) -> bool:
    """Check if a node is inside a subquery relative to outer_select."""
    parent = node.parent
    while parent is not None:
        if parent is outer_select:
            return False
        if isinstance(parent, (exp.Select, exp.Subquery)):
            return True
        parent = parent.parent
    return False
