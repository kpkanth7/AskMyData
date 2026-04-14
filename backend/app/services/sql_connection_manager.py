from urllib.parse import quote_plus
from uuid import uuid4

from sqlalchemy import MetaData, Table, create_engine, func, inspect, select

from app.models.sources import SourceKind, SourceMetadata, SourceType
from app.models.sources import SqlConnectionRequest
from app.services.schema_profiler import coerce_sample_value, profile_sql_columns
from app.services.workspace import SourceRuntime, workspace


def build_connection_string(request: SqlConnectionRequest) -> str:
    if request.connection_string:
        return request.connection_string
    if request.db_type == SourceType.sqlite:
        if not request.sqlite_path:
            raise ValueError("SQLite path is required when no connection string is provided.")
        return f"sqlite:///{request.sqlite_path}"
    if not all([request.host, request.port, request.user, request.database]):
        raise ValueError("Host, port, user, and database are required when no connection string is provided.")
    password = quote_plus(request.password or "")
    user = quote_plus(request.user or "")
    if request.db_type == SourceType.mysql:
        return f"mysql+pymysql://{user}:{password}@{request.host}:{request.port}/{request.database}"
    if request.db_type == SourceType.postgresql:
        return f"postgresql+psycopg://{user}:{password}@{request.host}:{request.port}/{request.database}"
    raise ValueError("Unsupported SQL database type.")


def connect_sql_source(request: SqlConnectionRequest) -> SourceMetadata:
    if request.db_type not in {SourceType.sqlite, SourceType.mysql, SourceType.postgresql}:
        raise ValueError("Only SQLite, MySQL, and PostgreSQL connections are supported.")

    connection_string = build_connection_string(request)
    engine = create_engine(connection_string, pool_pre_ping=True)
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if not table_names:
        raise ValueError("Connected successfully, but no tables were found.")

    primary_table = table_names[0]
    columns = profile_sql_columns(inspector.get_columns(primary_table))
    reflected_table = Table(primary_table, MetaData(), autoload_with=engine)
    row_count = None
    try:
        with engine.connect() as connection:
            row_count = int(connection.execute(select(func.count()).select_from(reflected_table)).scalar_one())
            sample_rows = connection.execute(select(reflected_table).limit(10)).mappings().all()
            columns = hydrate_sql_samples(columns, sample_rows)
    except Exception:
        row_count = None

    source_id = f"src_{uuid4().hex[:10]}"
    metadata = SourceMetadata(
        id=source_id,
        name=request.name,
        kind=SourceKind.sql,
        source_type=request.db_type,
        table_name=primary_table,
        row_count=row_count,
        columns=columns,
        notes=[f"Connected to {request.db_type.value}. Primary table selected: {primary_table}."],
    )
    workspace.add(SourceRuntime(metadata=metadata, engine=engine, sql_table=primary_table))
    return metadata


def hydrate_sql_samples(columns, sample_rows):
    hydrated = []
    for column in columns:
        values = []
        for row in sample_rows:
            value = row.get(column.name)
            if value is None:
                continue
            coerced = coerce_sample_value(value)
            if coerced not in values:
                values.append(coerced)
            if len(values) >= 10:
                break
        hydrated.append(column.model_copy(update={"sample_values": values}))
    return hydrated
