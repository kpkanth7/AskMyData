"use client";

import { DatabaseZap } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { connectSqlSource } from "@/lib/api";
import type { SqlConnectionPayload, WorkspaceState } from "@/types/api";

export function SqlConnectPanel({ workspace, onDone }: { workspace: WorkspaceState | null; onDone: () => void }) {
  const [useManual, setUseManual] = useState(false);
  const [payload, setPayload] = useState<SqlConnectionPayload>({ name: "", db_type: "postgresql", connection_string: "" });
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const remaining = workspace ? Math.max(workspace.max_total_files - workspace.sources.length, 0) : 5;

  async function submit() {
    setLoading(true);
    setMessage("");
    try {
      await connectSqlSource(payload);
      setMessage("Connected and moved to workspace.");
      setPayload({ name: "", db_type: "postgresql", connection_string: "" });
      setUseManual(false);
      onDone();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Connection failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-lg border border-ink/10 bg-white p-5 shadow-soft">
      <div className="flex items-center gap-2">
        <DatabaseZap className="h-5 w-5 text-coral" />
        <h2 className="font-semibold text-ink">Connect SQL</h2>
      </div>
      <p className="mt-1 text-sm text-ink/65">Use a connection string directly, or build one from manual fields. Database connections count as workspace sources.</p>

      <div className="mt-4 grid gap-3">
        <Input placeholder="Friendly source name" value={payload.name} onChange={(event) => setPayload({ ...payload, name: event.target.value })} />
        <select
          className="h-10 rounded-md border border-ink/15 bg-white px-3 text-sm outline-none focus:border-mint focus:ring-2 focus:ring-mint/20"
          value={payload.db_type}
          onChange={(event) => setPayload({ ...payload, db_type: event.target.value as SqlConnectionPayload["db_type"] })}
        >
          <option value="postgresql">PostgreSQL</option>
          <option value="mysql">MySQL</option>
          <option value="sqlite">SQLite</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-ink/70">
          <input type="checkbox" checked={useManual} onChange={(event) => setUseManual(event.target.checked)} />
          Use manual host/port/user/password/database fields
        </label>
        {!useManual ? (
          <Input placeholder="Connection string" value={payload.connection_string ?? ""} onChange={(event) => setPayload({ ...payload, connection_string: event.target.value })} />
        ) : payload.db_type === "sqlite" ? (
          <Input placeholder="SQLite file path on the backend host" value={payload.sqlite_path ?? ""} onChange={(event) => setPayload({ ...payload, sqlite_path: event.target.value, connection_string: "" })} />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <Input placeholder="Host" value={payload.host ?? ""} onChange={(event) => setPayload({ ...payload, host: event.target.value, connection_string: "" })} />
            <Input placeholder="Port" type="number" value={payload.port ?? ""} onChange={(event) => setPayload({ ...payload, port: Number(event.target.value), connection_string: "" })} />
            <Input placeholder="User" value={payload.user ?? ""} onChange={(event) => setPayload({ ...payload, user: event.target.value, connection_string: "" })} />
            <Input placeholder="Password" type="password" value={payload.password ?? ""} onChange={(event) => setPayload({ ...payload, password: event.target.value, connection_string: "" })} />
            <Input className="sm:col-span-2" placeholder="Database" value={payload.database ?? ""} onChange={(event) => setPayload({ ...payload, database: event.target.value, connection_string: "" })} />
          </div>
        )}
        {remaining <= 0 && <p className="rounded-md bg-coral/10 p-3 text-sm text-coral">This workspace is full. Remove a source before connecting another database.</p>}
        <Button onClick={submit} disabled={loading || !payload.name || remaining <= 0}>
          {loading ? "Connecting..." : "Connect source"}
        </Button>
        {message && <p className="text-sm text-ink/70">{message}</p>}
      </div>
    </div>
  );
}
