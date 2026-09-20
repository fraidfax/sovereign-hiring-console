"use client";

import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  fetchCandidates,
  fetchJob,
  runAgent,
  subscribeAgentStream,
} from "./lib/api";
import type { AgentEvent, Candidate, Job } from "./lib/types";
import { eventKey } from "./lib/eventKey";
import { DataResidencyBanner } from "./components/DataResidencyBanner";
import { ReasoningFeed } from "./components/ReasoningFeed";
import { CandidateCard } from "./components/CandidateCard";
import { AuditLogView } from "./components/AuditLogView";
import { ErrorBanner } from "./components/ErrorBanner";

const ACTOR_STORAGE_KEY = "sovereign-hiring-agent:actor";

function sortByScoreDesc(candidates: Candidate[]): Candidate[] {
  return [...candidates].sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
}

export default function DashboardPage() {
  const [job, setJob] = useState<Job | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);

  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [candidatesError, setCandidatesError] = useState<string | null>(null);

  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);
  const seenEventKeys = useRef<Set<string>>(new Set());
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [hasStarted, setHasStarted] = useState(false);
  const [isDone, setIsDone] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const [actor, setActor] = useState("");

  function refreshCandidates() {
    fetchCandidates()
      .then((data) => {
        setCandidates(data);
        setCandidatesError(null);
      })
      .catch((err: unknown) => {
        setCandidatesError(
          err instanceof ApiError ? err.message : "Could not load candidates.",
        );
      });
  }

  function scheduleCandidatesRefresh() {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    refreshTimer.current = setTimeout(refreshCandidates, 300);
  }

  useEffect(() => {
    fetchJob()
      .then(setJob)
      .catch((err: unknown) =>
        setJobError(err instanceof ApiError ? err.message : "Could not load the job posting."),
      );
    refreshCandidates();

    try {
      const saved = window.localStorage.getItem(ACTOR_STORAGE_KEY);
      if (saved) setActor(saved);
    } catch {
      // localStorage unavailable (private mode, etc.) — not fatal
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const source = subscribeAgentStream(
      (event) => {
        const key = eventKey(event);
        if (seenEventKeys.current.has(key)) return;
        seenEventKeys.current.add(key);
        setEvents((prev) => [...prev, event]);
        setHasStarted(true);
        setStreamError(null);
        if (event.type === "done") setIsDone(true);
        scheduleCandidatesRefresh();
      },
      (message) => setStreamError(message),
    );
    return () => {
      source.close();
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
    };
  }, []);

  function handleActorChange(value: string) {
    setActor(value);
    try {
      window.localStorage.setItem(ACTOR_STORAGE_KEY, value);
    } catch {
      // best-effort persistence only
    }
  }

  async function handleRunAgent() {
    setHasStarted(true);
    setRunError(null);
    try {
      await runAgent();
    } catch (err) {
      setRunError(err instanceof ApiError ? err.message : "Could not start the agent.");
      setHasStarted(false);
    }
  }

  const sortedCandidates = candidates ? sortByScoreDesc(candidates) : null;

  return (
    <main className="mx-auto max-w-6xl space-y-8 px-6 py-10">
      <header className="space-y-1">
        <h1 className="text-3xl font-bold tracking-tight text-slate-50">
          Sovereign Hiring Agent
        </h1>
        <p className="text-slate-400">
          An AI agent screens candidates with a human veto on every decision —
          built for data sovereignty.
        </p>
      </header>

      <DataResidencyBanner />

      <section className="rounded-xl border border-navy-600 bg-navy-900 p-5">
        {jobError && <ErrorBanner message={jobError} />}
        {!jobError && !job && (
          <p className="text-sm text-slate-500">Loading job posting…</p>
        )}
        {job && (
          <div>
            <h2 className="text-xl font-semibold text-slate-50">{job.title}</h2>
            <p className="text-sm text-slate-400">{job.location}</p>
            <p className="mt-2 text-sm text-slate-300">{job.description}</p>
            <p className="mt-2 text-xs text-slate-500">
              Requires {job.min_years_experience}+ years experience · must-have:{" "}
              {job.must_have_skills.join(", ")}
            </p>
          </div>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-4">
          <button
            type="button"
            onClick={handleRunAgent}
            disabled={hasStarted}
            className="rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-navy-950 transition hover:bg-accent-bright disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isDone ? "Agent run complete" : hasStarted ? "Running…" : "Run Agent"}
          </button>

          <label className="flex items-center gap-2 text-sm text-slate-400">
            Reviewer name:
            <input
              type="text"
              value={actor}
              onChange={(e) => handleActorChange(e.target.value)}
              placeholder="Your name"
              className="rounded-lg border border-navy-600 bg-navy-800 px-3 py-1.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-accent focus:outline-none"
            />
          </label>
        </div>
        <ErrorBanner message={runError} />
        <ErrorBanner message={streamError} />
      </section>

      <section className="rounded-xl border border-navy-600 bg-navy-900 p-5">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">
          Live agent reasoning
        </h2>
        <ReasoningFeed events={events} />
      </section>

      <section className="space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Candidates
        </h2>
        <ErrorBanner message={candidatesError} />
        {!candidatesError && sortedCandidates === null && (
          <p className="text-sm text-slate-500">Loading candidates…</p>
        )}
        {sortedCandidates && sortedCandidates.length === 0 && (
          <p className="text-sm text-slate-500">No candidates found.</p>
        )}
        <div className="space-y-4">
          {sortedCandidates?.map((candidate) => (
            <CandidateCard
              key={candidate.id}
              candidate={candidate}
              actor={actor}
              onDecided={refreshCandidates}
            />
          ))}
        </div>
      </section>

      <AuditLogView />
    </main>
  );
}
