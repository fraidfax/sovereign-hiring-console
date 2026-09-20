import { Fragment } from "react";
import type { AgentEvent } from "../lib/types";
import { eventKey } from "../lib/eventKey";

const TYPE_META: Record<
  AgentEvent["type"],
  { icon: string; label: string; className: string }
> = {
  tool_call: { icon: "→", label: "Tool call", className: "text-slate-300" },
  tool_result: { icon: "✓", label: "Tool result", className: "text-accent-bright" },
  narration: { icon: "…", label: "Narration", className: "text-slate-400" },
  recommendation: {
    icon: "★",
    label: "Recommendation",
    className: "text-warn",
  },
  done: { icon: "●", label: "Run complete", className: "text-slate-500" },
};

function formatTs(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleTimeString([], { hour12: false });
}

function DetailView({ detail }: { detail: unknown }) {
  if (detail === null || detail === undefined) return null;
  if (typeof detail === "string") {
    return <span>{detail}</span>;
  }
  if (typeof detail === "number" || typeof detail === "boolean") {
    return <span>{String(detail)}</span>;
  }
  if (Array.isArray(detail)) {
    if (detail.length === 0) return null;
    return (
      <ul className="list-inside list-disc space-y-0.5">
        {detail.map((item, i) => (
          <li key={i}>
            {typeof item === "object" ? JSON.stringify(item) : String(item)}
          </li>
        ))}
      </ul>
    );
  }
  const entries = Object.entries(detail as Record<string, unknown>);
  if (entries.length === 0) return null;
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
      {entries.map(([key, value]) => (
        <Fragment key={key}>
          <dt className="font-medium text-slate-400">{key}</dt>
          <dd className="break-words text-slate-200">
            {typeof value === "object"
              ? JSON.stringify(value)
              : String(value)}
          </dd>
        </Fragment>
      ))}
    </dl>
  );
}

function FeedEntry({ event }: { event: AgentEvent }) {
  const meta = TYPE_META[event.type];
  const isRecommendation = event.type === "recommendation";
  const isNarration = event.type === "narration";

  return (
    <div
      className={
        isRecommendation
          ? "rounded-lg border border-warn/50 bg-warn-dim/20 p-3"
          : "rounded-lg border border-navy-600/60 bg-navy-800/60 p-3"
      }
    >
      <div className="flex items-center gap-2 text-xs">
        <span aria-hidden className={`text-base leading-none ${meta.className}`}>
          {meta.icon}
        </span>
        <span className={`font-semibold uppercase tracking-wide ${meta.className}`}>
          {meta.label}
        </span>
        {event.tool && (
          <span className="rounded bg-navy-700 px-1.5 py-0.5 font-mono text-[11px] text-slate-300">
            {event.tool}
          </span>
        )}
        <span className="ml-auto font-mono text-[11px] text-slate-500">
          {formatTs(event.ts)}
        </span>
      </div>
      <div
        className={
          isNarration
            ? "mt-1.5 text-sm italic text-slate-300"
            : "mt-1.5 text-sm text-slate-200"
        }
      >
        <DetailView detail={event.detail} />
      </div>
    </div>
  );
}

interface Group {
  candidateId: string | null;
  events: AgentEvent[];
}

function groupByCandidate(events: AgentEvent[]): Group[] {
  const groups: Group[] = [];
  for (const event of events) {
    const last = groups[groups.length - 1];
    if (last && last.candidateId === event.candidate_id) {
      last.events.push(event);
    } else {
      groups.push({ candidateId: event.candidate_id, events: [event] });
    }
  }
  return groups;
}

export function ReasoningFeed({ events }: { events: AgentEvent[] }) {
  if (events.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        No agent activity yet. Run the agent to see it reason through each
        candidate, live.
      </p>
    );
  }

  const groups = groupByCandidate(events);

  return (
    <div className="max-h-[32rem] space-y-4 overflow-y-auto pr-1">
      {groups.map((group, i) => (
        <div
          key={`${group.candidateId ?? "agent"}-${i}`}
          className="rounded-xl border border-navy-600 bg-navy-900/60 p-3"
        >
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
            {group.candidateId ? `Candidate ${group.candidateId}` : "Agent"}
          </div>
          <div className="space-y-2">
            {group.events.map((event) => (
              <FeedEntry key={eventKey(event)} event={event} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
