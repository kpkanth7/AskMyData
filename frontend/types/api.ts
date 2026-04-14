export type ColumnProfile = {
  name: string;
  dtype: string;
  null_count: number;
  unique_count: number;
  sample_values: unknown[];
};

export type SourceMetadata = {
  id: string;
  name: string;
  kind: "file" | "sql";
  source_type: "csv" | "xlsx" | "sqlite" | "mysql" | "postgresql";
  table_name: string;
  row_count?: number | null;
  columns: ColumnProfile[];
  notes: string[];
};

export type WorkspaceState = {
  sources: SourceMetadata[];
  uploaded_file_count: number;
  max_total_files: number;
  max_file_size_mb: number;
};

export type SqlConnectionPayload = {
  name: string;
  db_type: "sqlite" | "mysql" | "postgresql";
  connection_string?: string;
  host?: string;
  port?: number;
  user?: string;
  password?: string;
  database?: string;
  sqlite_path?: string;
};

export type ChartSpec = {
  enabled: boolean;
  chart_type?: "bar" | "horizontal_bar" | "line" | "area" | "pie" | "radial_bar" | "treemap" | "radar" | "scatter" | "histogram" | null;
  x_key?: string | null;
  y_key?: string | null;
  title?: string | null;
};

export type ResultBlock = {
  id: string;
  label: string;
  source_name: string;
  question: string;
  rows: Record<string, unknown>[];
  columns: string[];
  sql?: string | null;
  chart: ChartSpec;
};

export type QueryResponse = {
  needs_join_confirmation: boolean;
  join_confirmation_message?: string | null;
  needs_source_confirmation: boolean;
  source_confirmation_message?: string | null;
  candidate_sources: {
    id: string;
    name: string;
    columns: string[];
  }[];
  result_blocks: ResultBlock[];
  final_summary?: string | null;
  debug?: Record<string, unknown> | null;
};
