import { Database, FileSpreadsheet, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { SourceMetadata } from "@/types/api";

export function SourceCard({ source, onRemove, removing = false }: { source: SourceMetadata; onRemove?: (sourceId: string) => void; removing?: boolean }) {
  const Icon = source.kind === "file" ? FileSpreadsheet : Database;
  return (
    <div className="rounded-lg border border-ink/10 bg-white p-4 transition hover:-translate-y-0.5 hover:border-mint/40 hover:shadow-soft">
      <div className="flex items-start gap-3">
        <div className="rounded-md bg-mint/12 p-2 text-mint">
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold text-ink">{source.name}</p>
          <p className="text-xs uppercase tracking-normal text-ink/55">
            {source.source_type} · {source.table_name}
          </p>
        </div>
        {onRemove && (
          <Button size="sm" variant="ghost" onClick={() => onRemove(source.id)} disabled={removing} title={`Remove ${source.name}`}>
            <Trash2 className="mr-1 h-4 w-4" />
            {removing ? "Removing" : "Remove"}
          </Button>
        )}
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        <span className="rounded-md bg-cloud px-2 py-1 text-ink/70">{source.row_count ?? "?"} rows</span>
        <span className="rounded-md bg-cloud px-2 py-1 text-ink/70">{source.columns.length} columns</span>
        <span className="rounded-md bg-cloud px-2 py-1 text-ink/70">{source.kind === "sql" ? "Database" : "File"}</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {source.columns.slice(0, 6).map((column) => (
          <span key={column.name} className="rounded-md border border-ink/10 px-2 py-1 text-xs text-ink/65">
            {column.name}
          </span>
        ))}
      </div>
      {source.columns.length > 6 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-semibold text-ink/60">Show all columns</summary>
          <div className="mt-2 flex max-h-28 flex-wrap gap-1.5 overflow-auto rounded-md bg-cloud p-2">
            {source.columns.map((column) => (
              <span key={column.name} className="rounded-md bg-white px-2 py-1 text-xs text-ink/65 ring-1 ring-ink/10">
                {column.name}
              </span>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
