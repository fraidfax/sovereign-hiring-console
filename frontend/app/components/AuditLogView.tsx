"use client";

import { useEffect, useState } from "react";
import { fetchAuditLog, ApiError } from "../lib/api";
import type { AuditLogEntry } from "../lib/types";
import { ErrorBanner } from "./ErrorBanner";

function summarize(entry: AuditLogEntry): string {
  const who = entry.candidate_id ? `candidate ${entry.candidate_id}` : "a candidate";
  if (entry.event === "ai_recommendation") {
    const rec = entry.recommendation ? entry.recommendation.toUpperCase() : "a recommendation";
    return `Agent recommended ${rec} for ${who}.`;
  }
  if (entry.event === "human_decision") {
    const actor = entry.actor ?? "A reviewer";
    const decision = entry.decision ? entry.decision.toUpperCase() : "a decision";
    const overrideNote = entry.is_override ? " — this overrode the agent" : "";
    return `${actor} recorded ${decision} for ${who}${overrideNote}.`;
  }
  return `${entry.event} for ${who}.`;
}

function formatTs(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString([], { hour12: false });
}

export function AuditLogView() {
  const [entries, setEntries] = useState<AuditLogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  function load() {
    setLoading(true);
    setError(null);
    fetchAuditLog()
      .then(setEntries)
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : "Could not load the audit log."),
      )
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (open && entries === null) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <section className="rounded-xl border border-navy-600 bg-navy-900 p-5">
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 text-sm font-semibold text-slate-200"
        >
          <span aria-hidden className={`transition ${open ? "rotate-90" : ""}`}>
            ▸
          </span>
          Audit log
        </button>
        {open && (
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="text-xs text-accent hover:text-accent-bright disabled:opacity-40"
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        )}
      </div>

      {open && (
        <div className="mt-4">
          <ErrorBanner message={error} />
          {loading && entries === null && (
            <p className="text-sm text-slate-500">Loading audit log…</p>
          )}
          {entries !== null && entries.length === 0 && (
            <p className="text-sm text-slate-500">No audit events yet.</p>
          )}
          {entries !== null && entries.length > 0 && (
            <ol className="max-h-96 space-y-2 overflow-y-auto pr-1">
              {entries.map((entry, i) => (
                <li
                  key={`${entry.ts}-${i}`}
                  className="rounded-lg border border-navy-600 bg-navy-800/60 p-2.5 text-sm"
                >
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="font-mono text-xs text-slate-500">
                      {formatTs(entry.ts)}
                    </span>
                    <span className="rounded bg-navy-700 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      {entry.event}
                    </span>
                  </div>
                  <p className="mt-1 text-slate-200">{summarize(entry)}</p>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}
