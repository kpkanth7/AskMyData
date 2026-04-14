"use client";

import { Info, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { uploadFiles } from "@/lib/api";
import type { WorkspaceState } from "@/types/api";

export function UploadPanel({ workspace, onDone }: { workspace: WorkspaceState | null; onDone: () => void }) {
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [message, setMessage] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const totalSources = workspace?.sources.length ?? 0;
  const remaining = workspace ? Math.max(workspace.max_total_files - totalSources, 0) : 5;

  function handleFileSelection(files: File[]) {
    setMessage("");
    if (files.length > remaining) {
      setPendingFiles([]);
      if (inputRef.current) inputRef.current.value = "";
      setMessage(`You can add ${remaining} more source${remaining === 1 ? "" : "s"} to this workspace.`);
      return;
    }
    setPendingFiles(files);
  }

  async function submit(shouldClean: boolean) {
    setLoading(true);
    setMessage("");
    try {
      await uploadFiles(pendingFiles, shouldClean);
      setPendingFiles([]);
      if (inputRef.current) inputRef.current.value = "";
      setMessage(shouldClean ? "Moved to workspace with light cleaning applied." : "Moved to workspace without cleaning.");
      onDone();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-lg border border-dashed border-ink/20 bg-white p-5 shadow-soft">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <UploadCloud className="h-5 w-5 text-mint" />
            <h2 className="font-semibold text-ink">Add files</h2>
          </div>
          <p className="mt-1 text-sm text-ink/65">
            {remaining} of {workspace?.max_total_files ?? 5} source slots available. Files can be up to {workspace?.max_file_size_mb ?? 10} MB each.
          </p>
        </div>
        <div className="group relative">
          <Info className="h-5 w-5 text-coral" />
          <div className="absolute right-0 z-10 mt-2 hidden w-64 rounded-md border border-ink/10 bg-white p-3 text-xs text-ink/70 shadow-soft group-hover:block">
            Supported source types: CSV, XLSX, SQLite, MySQL, and PostgreSQL connections. SQL dump uploads are not supported yet.
          </div>
        </div>
      </div>

      <input
        ref={inputRef}
        className="mt-4 block w-full cursor-pointer rounded-md border border-ink/10 bg-cloud p-3 text-sm text-ink file:mr-3 file:rounded-md file:border-0 file:bg-ink file:px-3 file:py-2 file:text-white"
        type="file"
        multiple
        accept=".csv,.xlsx"
        disabled={remaining <= 0 || loading}
        onChange={(event) => handleFileSelection(Array.from(event.target.files ?? []))}
      />

      {remaining <= 0 && <p className="mt-3 rounded-md bg-coral/10 p-3 text-sm text-coral">This workspace already has {workspace?.max_total_files ?? 5} sources. Remove a source before adding another file or connection.</p>}

      {pendingFiles.length > 0 && (
        <div className="mt-4 rounded-md bg-[#edf9f4] p-4">
          <div className="mb-3 flex flex-wrap gap-2">
            {pendingFiles.map((file) => (
              <span key={`${file.name}-${file.size}`} className="rounded-md bg-white px-2 py-1 text-xs font-medium text-ink/70 ring-1 ring-ink/10">
                {file.name}
              </span>
            ))}
          </div>
          <p className="font-medium text-ink">Do you want to clean the data slightly before we fetch results for your query?</p>
          <p className="mt-1 text-sm text-ink/65">This will only apply light, non-extensive cleaning.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => submit(true)} disabled={loading}>
              Yes, clean lightly
            </Button>
            <Button size="sm" variant="secondary" onClick={() => submit(false)} disabled={loading}>
              No, upload as-is
            </Button>
          </div>
        </div>
      )}
      {message && <p className="mt-3 text-sm text-ink/70">{message}</p>}
    </div>
  );
}
