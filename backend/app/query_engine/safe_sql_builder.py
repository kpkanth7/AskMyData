from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from app.models.query import OperationSpec
from app.models.sources import SourceMetadata


def quote_identifier(identifier: str, dialect: str = "duckdb") -> str:
    if dialect == "mysql":
        return "`" + identifier.replace("`", "``") + "`"
    return '"' + identifier.replace('"', '""') + '"'


def validate_columns(operation: OperationSpec, metadata: SourceMetadata) -> None:
    valid = {column.name for column in metadata.columns}
    requested = set(operation.select_columns + operation.group_by)
    if operation.aggregate_column:
        requested.add(operation.aggregate_column)
    if operation.sort_by:
        requested.add(operation.sort_by)
    for filter_spec in operation.filters:
        requested.add(filter_spec.column)
    unknown = requested - valid
    if unknown:
        raise ValueError(f"Unknown or unsafe columns requested: {', '.join(sorted(unknown))}")


def build_select_sql(
    table_name: str,
    metadata: SourceMetadata,
    operation: OperationSpec,
    dialect: str = "duckdb",
    named_params: bool = False,
) -> Tuple[str, List[object] | Dict[str, object]]:
    validate_columns(operation, metadata)
    params: List[object] | Dict[str, object] = {} if named_params else []
    table = quote_identifier(table_name, dialect)

    if operation.aggregate:
        metric = build_metric(operation, dialect)
        group_by = [quote_identifier(column, dialect) for column in operation.group_by]
        select_parts = group_by + [metric]
    elif operation.select_columns:
        select_parts = [quote_identifier(column, dialect) for column in operation.select_columns]
    else:
        select_parts = ["*"]

    sql = f"SELECT {', '.join(select_parts)} FROM {table}"
    where_clauses: List[str] = []
    for filter_spec in operation.filters:
        column = quote_identifier(filter_spec.column, dialect)
        param_name = f"p{len(params)}"
        placeholder = f":{param_name}" if named_params else "?"
        if filter_spec.operator == "contains":
            where_clauses.append(build_contains_clause(column, placeholder, dialect))
            add_param(params, param_name, f"%{filter_spec.value}%")
        else:
            operator_map = {"eq": "=", "neq": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
            where_clauses.append(f"{column} {operator_map[filter_spec.operator.value]} {placeholder}")
            add_param(params, param_name, filter_spec.value)
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    if operation.group_by:
        sql += " GROUP BY " + ", ".join(quote_identifier(column, dialect) for column in operation.group_by)

    if operation.aggregate and operation.group_by and (not operation.sort_by or operation.sort_by not in operation.group_by):
        sql += f" ORDER BY metric {operation.sort_direction.value.upper()}"
    elif operation.sort_by:
        sql += f" ORDER BY {quote_identifier(operation.sort_by, dialect)} {operation.sort_direction.value.upper()}"
    elif operation.aggregate and operation.group_by:
        sql += " ORDER BY metric DESC"

    sql += f" LIMIT {operation.limit}"
    validate_sql_statement(sql, dialect)
    return sql, params


def build_contains_clause(column: str, placeholder: str, dialect: str) -> str:
    if dialect in {"duckdb", "postgresql"}:
        return f"CAST({column} AS TEXT) ILIKE {placeholder}"
    if dialect == "mysql":
        return f"LOWER(CAST({column} AS CHAR)) LIKE LOWER({placeholder})"
    return f"LOWER(CAST({column} AS TEXT)) LIKE LOWER({placeholder})"


def build_metric(operation: OperationSpec, dialect: str = "duckdb") -> str:
    if operation.aggregate.value == "count":
        return "COUNT(*) AS metric"
    if not operation.aggregate_column:
        return "COUNT(*) AS metric"
    return f'{operation.aggregate.value.upper()}({quote_identifier(operation.aggregate_column, dialect)}) AS metric'


def add_param(params: List[object] | Dict[str, object], name: str, value: object) -> None:
    if isinstance(params, dict):
        params[name] = value
    else:
        params.append(value)


def format_sql_preview(sql: str, params: List[object] | Dict[str, object]) -> str:
    if isinstance(params, dict):
        preview = sql
        for name, value in sorted(params.items(), key=lambda item: len(item[0]), reverse=True):
            preview = preview.replace(f":{name}", sql_literal(value))
        return preview

    preview = sql
    for value in params:
        preview = preview.replace("?", sql_literal(value), 1)
    return preview


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def validate_sql_statement(sql: str, dialect: str) -> None:
    lower = sql.lower()
    blocked = ("insert ", "update ", "delete ", "drop ", "alter ", "truncate ", "create ")
    if any(keyword in lower for keyword in blocked):
        raise ValueError("Unsafe SQL statement detected.")
    if not lower.strip().startswith("select "):
        raise ValueError("Only SELECT statements are allowed.")
    try:
        import sqlglot

        read_dialect = "postgres" if dialect == "postgresql" else ("mysql" if dialect == "mysql" else "duckdb")
        parsed = sqlglot.parse_one(sql, read=read_dialect)
        if parsed is None or parsed.key.lower() != "select":
            raise ValueError("Only SELECT statements are allowed.")
    except ImportError:
        # Optional dependency: keyword checks above remain active even without sqlglot installed.
        return


def prepare_raw_select_sql(
    sql: str,
    metadata: SourceMetadata,
    dialect: str = "duckdb",
    allow_joins: bool = False,
    default_limit: int = 10,
    max_limit: int = 500,
) -> str:
    cleaned = sql.strip().rstrip(";")
    validate_sql_statement(cleaned, dialect)
    validate_raw_sql_shape(cleaned, metadata, dialect, allow_joins)
    return enforce_sql_limit(cleaned, default_limit=default_limit, max_limit=max_limit)


def validate_raw_sql_shape(sql: str, metadata: SourceMetadata, dialect: str, allow_joins: bool) -> None:
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:
        fallback_validate_raw_sql(sql, metadata, allow_joins)
        return

    read_dialect = "postgres" if dialect == "postgresql" else ("mysql" if dialect == "mysql" else "duckdb")
    statements = sqlglot.parse(sql, read=read_dialect)
    if len(statements) != 1:
        raise ValueError("Only one SELECT statement is allowed.")
    parsed = statements[0]
    if parsed is None or parsed.key.lower() != "select":
        raise ValueError("Only SELECT statements are allowed.")
    if parsed.args.get("with"):
        raise ValueError("CTEs are not allowed in generated SQL yet.")

    tables = {table.name for table in parsed.find_all(exp.Table)}
    if not tables:
        raise ValueError("Generated SQL must include the selected source table.")
    if metadata.table_name not in tables:
        raise ValueError("Generated SQL references a table outside the selected source.")
    if not allow_joins and (len(tables) > 1 or any(True for _ in parsed.find_all(exp.Join))):
        raise ValueError("Generated SQL requires a join, but joins were not confirmed.")

    valid_columns = {column.name for column in metadata.columns}
    aliases = {alias.alias for alias in parsed.find_all(exp.Alias) if alias.alias}
    for column in parsed.find_all(exp.Column):
        if column.name == "*":
            continue
        if column.name not in valid_columns and column.name not in aliases:
            raise ValueError(f"Generated SQL references unknown column: {column.name}")


def fallback_validate_raw_sql(sql: str, metadata: SourceMetadata, allow_joins: bool) -> None:
    lower = sql.lower()
    if metadata.table_name.lower() not in lower:
        raise ValueError("Generated SQL must include the selected source table.")
    if not allow_joins and " join " in lower:
        raise ValueError("Generated SQL requires a join, but joins were not confirmed.")


def enforce_sql_limit(sql: str, default_limit: int = 10, max_limit: int = 500) -> str:
    limit_match = re.search(r"\blimit\s+(\d+)\b", sql, flags=re.IGNORECASE)
    if not limit_match:
        return f"{sql} LIMIT {default_limit}"
    limit = int(limit_match.group(1))
    if limit > max_limit:
        return re.sub(r"\blimit\s+\d+\b", f"LIMIT {max_limit}", sql, count=1, flags=re.IGNORECASE)
    return sql
