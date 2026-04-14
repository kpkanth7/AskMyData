"use client";

import { MessageSquareText, RefreshCw, Sparkles } from "lucide-react";
import Image from "next/image";
import { useEffect, useState } from "react";

import { ResultsView } from "@/components/results-view";
import { SourceCard } from "@/components/source-card";
import { SqlConnectPanel } from "@/components/sql-connect-panel";
import { UploadPanel } from "@/components/upload-panel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { askQuestion, fetchWorkspace, removeSource } from "@/lib/api";
import type { QueryResponse, WorkspaceState } from "@/types/api";

export default function Home() {
  const [workspace, setWorkspace] = useState<WorkspaceState | null>(null);
  const [question, setQuestion] = useState("");
  const [lastQuestion, setLastQuestion] = useState("");
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [joinPrompt, setJoinPrompt] = useState<string | null>(null);
  const [sourcePrompt, setSourcePrompt] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [removingSourceId, setRemovingSourceId] = useState<string | null>(null);

  async function refresh() {
    setWorkspace(await fetchWorkspace());
  }

  useEffect(() => {
    refresh().catch((err) => setError(err.message));
  }, []);

  async function submit(allowJoins = false, preferredSourceId?: string) {
    if (!question.trim() && !lastQuestion) {
      setError("Ask a question first.");
      return;
    }
    if (!workspace?.sources.length) {
      setError("Add a CSV, XLSX, SQLite, MySQL, or PostgreSQL source first.");
      return;
    }
    const activeQuestion = question.trim() || lastQuestion;
    setLoading(true);
    setError("");
    setJoinPrompt(null);
    setSourcePrompt(null);
    try {
      const result = await askQuestion(activeQuestion, allowJoins, preferredSourceId);
      if (result.needs_source_confirmation) {
        setLastQuestion(activeQuestion);
        setSourcePrompt(result);
        return;
      }
      if (result.needs_join_confirmation) {
        setLastQuestion(activeQuestion);
        setJoinPrompt(result.join_confirmation_message ?? "This question may require combining two datasets. Should joins be permitted for this query?");
        return;
      }
      setResponse(result);
      setLastQuestion(activeQuestion);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Query failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleRemoveSource(sourceId: string) {
    setError("");
    setRemovingSourceId(sourceId);
    try {
      await removeSource(sourceId);
      await refresh();
      setResponse(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove source");
    } finally {
      setRemovingSourceId(null);
    }
  }

  return (
    <main className="min-h-screen">
      <section className="mx-auto grid w-full max-w-7xl gap-6 px-4 py-6 lg:grid-cols-[390px_1fr] lg:px-8">
        <aside className="space-y-5">
          <div className="overflow-hidden rounded-lg border border-ink/10 bg-white shadow-soft">
            <Image
              src="https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=1200&q=80"
              alt="Analytics workspace"
              width={1200}
              height={480}
              priority
              className="h-40 w-full object-cover"
            />
            <div className="p-5">
              <div className="flex items-center gap-2 text-coral">
                <Sparkles className="h-5 w-5" />
                <p className="text-sm font-semibold uppercase tracking-normal">askmydata</p>
              </div>
              <h1 className="mt-3 text-3xl font-bold leading-tight text-ink">Ask natural-language questions over your own data.</h1>
              <p className="mt-3 text-sm leading-6 text-ink/65">Turn messy tables into clear answers, charts when they help, and one grounded takeaway you can trust.</p>
            </div>
          </div>

          <UploadPanel workspace={workspace} onDone={refresh} />
          <SqlConnectPanel workspace={workspace} onDone={refresh} />
        </aside>

        <section className="space-y-5">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Workspace sources</CardTitle>
                <p className="text-sm text-ink/60">No session history is saved.</p>
              </div>
              <Button variant="secondary" size="sm" onClick={refresh}>
                <RefreshCw className="mr-2 h-4 w-4" />
                Refresh
              </Button>
            </CardHeader>
            <CardContent>
              {workspace?.sources.length ? (
                <div className="grid gap-3 md:grid-cols-2">
                  {workspace.sources.map((source) => (
                    <SourceCard key={source.id} source={source} onRemove={handleRemoveSource} removing={removingSourceId === source.id} />
                  ))}
                </div>
              ) : (
                <div className="rounded-lg border border-ink/10 bg-cloud p-6 text-center text-ink/60">Add a file or SQL connection to start asking questions.</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <MessageSquareText className="h-5 w-5 text-mint" />
                <CardTitle>Ask</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <Textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Example: Show top 10 customers by revenue, or compare monthly sales trends across each dataset."
              />
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button onClick={() => submit(false)} disabled={loading}>
                  {loading ? "Working..." : "Ask my data"}
                </Button>
                {error && <p className="text-sm text-coral">{error}</p>}
              </div>
              {joinPrompt && (
                <div className="mt-4 rounded-md bg-[#fff3ef] p-4">
                  <p className="font-medium text-ink">{joinPrompt}</p>
                  <div className="mt-3 flex gap-2">
                    <Button variant="accent" size="sm" onClick={() => submit(true)} disabled={loading}>
                      Permit joins for this query
                    </Button>
                    <Button variant="secondary" size="sm" onClick={() => setJoinPrompt(null)}>
                      Not now
                    </Button>
                  </div>
                </div>
              )}
              {sourcePrompt?.needs_source_confirmation && (
                <div className="mt-4 rounded-md bg-[#edf9f4] p-4">
                  <p className="font-medium text-ink">{sourcePrompt.source_confirmation_message}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {sourcePrompt.candidate_sources.map((source) => (
                      <Button key={source.id} variant="secondary" size="sm" onClick={() => submit(false, source.id)} disabled={loading}>
                        Use {source.name}
                      </Button>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <ResultsView response={response} />
        </section>
      </section>
    </main>
  );
}
