import type { Candidate, CandidateStatus } from "../lib/types";
import { RedactionReveal } from "./RedactionReveal";
import { ApprovalGate } from "./ApprovalGate";
import { RegulationBadges } from "./RegulationBadge";

const STATUS_STYLE: Record<CandidateStatus, string> = {
  not_started: "bg-navy-700 text-slate-400",
  processing: "bg-sky-900 text-sky-300 animate-pulse",
  pending_review: "bg-warn-dim/60 text-warn",
  approved: "bg-accent-dim/30 text-accent-bright",
  rejected: "bg-red-950 text-red-300",
};

const STATUS_LABEL: Record<CandidateStatus, string> = {
  not_started: "Not started",
  processing: "Processing…",
  pending_review: "Pending review",
  approved: "Approved",
  rejected: "Rejected",
};

function SkillPills({
  skills,
  tone,
}: {
  skills: string[];
  tone: "match" | "miss";
}) {
  if (skills.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-1.5">
      {skills.map((s) => (
        <li
          key={s}
          className={
            tone === "match"
              ? "rounded-full bg-accent-dim/20 px-2 py-0.5 text-xs text-accent-bright"
              : "rounded-full bg-navy-700 px-2 py-0.5 text-xs text-slate-500 line-through"
          }
        >
          {s}
        </li>
      ))}
    </ul>
  );
}

interface CandidateCardProps {
  candidate: Candidate;
  actor: string;
  onDecided: () => void;
}

export function CandidateCard({ candidate, actor, onDecided }: CandidateCardProps) {
  const p = candidate.redacted_profile;

  return (
    <article className="rounded-2xl border border-navy-600 bg-navy-900 p-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-semibold text-slate-50">
            Candidate {p.id}
          </h3>
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-semibold ${STATUS_STYLE[candidate.status]}`}
          >
            {STATUS_LABEL[candidate.status]}
          </span>
        </div>
        <div className="text-2xl font-bold text-accent-bright">
          {candidate.score !== null ? candidate.score.toFixed(0) : "—"}
          <span className="ml-1 text-sm font-normal text-slate-500">/ 100</span>
        </div>
      </header>

      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-slate-400 sm:grid-cols-4">
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-600">
            Experience
          </dt>
          <dd>{p.years_experience} yrs</dd>
        </div>
        <div className="col-span-3">
          <dt className="text-xs uppercase tracking-wide text-slate-600">
            Education
          </dt>
          <dd>{p.education}</dd>
        </div>
      </dl>

      {candidate.explanation && (
        <p className="mt-3 text-sm text-slate-300">{candidate.explanation}</p>
      )}

      <div className="mt-3 space-y-2">
        {candidate.matched_must_haves.length > 0 && (
          <div>
            <p className="mb-1 text-xs uppercase tracking-wide text-slate-600">
              Matched must-haves
            </p>
            <SkillPills skills={candidate.matched_must_haves} tone="match" />
          </div>
        )}
        {candidate.missing_must_haves.length > 0 && (
          <div>
            <p className="mb-1 text-xs uppercase tracking-wide text-slate-600">
              Missing must-haves
            </p>
            <SkillPills skills={candidate.missing_must_haves} tone="miss" />
          </div>
        )}
        {candidate.matched_nice_to_haves.length > 0 && (
          <div>
            <p className="mb-1 text-xs uppercase tracking-wide text-slate-600">
              Matched nice-to-haves
            </p>
            <SkillPills skills={candidate.matched_nice_to_haves} tone="match" />
          </div>
        )}
      </div>

      <div className="mt-4">
        <RedactionReveal
          removedFields={candidate.removed_fields}
          scrubbedSpans={candidate.scrubbed_spans}
        />
      </div>

      {candidate.bias_note && (
        <p className="mt-3 rounded-lg border border-navy-600 bg-navy-800/60 p-2.5 text-sm text-slate-400">
          <span className="mr-1 font-semibold text-slate-300">Bias check:</span>
          {candidate.bias_note}
        </p>
      )}

      {candidate.recommendation && (
        <div className="mt-3 rounded-lg border border-navy-600 bg-navy-800/60 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Agent recommendation:{" "}
            <span
              className={
                candidate.recommendation === "approve"
                  ? "text-accent-bright"
                  : "text-warn"
              }
            >
              {candidate.recommendation}
            </span>
          </p>
          {candidate.recommendation_reasoning && (
            <p className="mt-1 text-sm text-slate-300">
              {candidate.recommendation_reasoning}
            </p>
          )}
        </div>
      )}

      <div className="mt-4 space-y-3">
        <RegulationBadges />
        <ApprovalGate candidate={candidate} actor={actor} onDecided={onDecided} />
      </div>
    </article>
  );
}
