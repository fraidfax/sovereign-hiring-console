"use client";

import { useState } from "react";
import { decide, ApiError } from "../lib/api";
import type { Candidate, Recommendation } from "../lib/types";

function DecisionRecord({ candidate }: { candidate: Candidate }) {
  if (candidate.status !== "approved" && candidate.status !== "rejected") {
    return null;
  }
  return (
    <div className="rounded-xl border border-navy-600 bg-navy-900/60 p-4">
      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-slate-500">
        <span aria-hidden>{candidate.status === "approved" ? "✓" : "✕"}</span>
        Decision recorded: {candidate.status}
      </div>
      <p className="mt-2 text-sm text-slate-300">
        {candidate.decision_actor && (
          <>
            By{" "}
            <span className="font-medium text-slate-100">
              {candidate.decision_actor}
            </span>
            .{" "}
          </>
        )}
        {candidate.is_override
          ? "This overrode the agent's recommendation."
          : "This accepted the agent's recommendation."}
      </p>
      {candidate.decision_reason && (
        <p className="mt-1 text-sm text-slate-400">
          Reason: {candidate.decision_reason}
        </p>
      )}
    </div>
  );
}

interface ApprovalGateProps {
  candidate: Candidate;
  actor: string;
  onDecided: () => void;
}

export function ApprovalGate({ candidate, actor, onDecided }: ApprovalGateProps) {
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [overrideChoice, setOverrideChoice] = useState<Recommendation | null>(
    null,
  );
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (candidate.status !== "pending_review") {
    return <DecisionRecord candidate={candidate} />;
  }

  const recommendation = candidate.recommendation;
  const opposite: Recommendation | null =
    recommendation === "approve"
      ? "reject"
      : recommendation === "reject"
        ? "approve"
        : null;
  const actorReady = actor.trim().length > 0;

  async function submit(decision: Recommendation, isOverride: boolean) {
    if (!actorReady) {
      setError("Enter your name in the reviewer field above first.");
      return;
    }
    if (isOverride && reason.trim().length === 0) {
      setError("A written reason is required to override the recommendation.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await decide({
        candidate_id: candidate.id,
        decision,
        actor: actor.trim(),
        reason: isOverride ? reason.trim() : undefined,
      });
      setReason("");
      setOverrideOpen(false);
      onDecided();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not record the decision.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-xl border-2 border-warn/60 bg-navy-900 p-4">
      <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-warn">
        <span aria-hidden>⚑</span>
        Human decision required
      </div>

      {recommendation && (
        <p className="mb-3 text-sm text-slate-300">
          The agent recommends{" "}
          <span
            className={
              recommendation === "approve"
                ? "font-semibold text-accent-bright"
                : "font-semibold text-warn"
            }
          >
            {recommendation === "approve" ? "APPROVE" : "REJECT"}
          </span>
          . No decision is final until a human confirms it.
        </p>
      )}

      {error && <p className="mb-2 text-sm text-red-300">{error}</p>}
      {!actorReady && (
        <p className="mb-2 text-xs text-slate-500">
          Enter your name in the reviewer field above to enable decisions.
        </p>
      )}

      {!overrideOpen && (
        <div className="flex flex-wrap items-center gap-3">
          {recommendation && (
            <button
              type="button"
              disabled={!actorReady || submitting}
              onClick={() => submit(recommendation, false)}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-navy-950 transition hover:bg-accent-bright disabled:cursor-not-allowed disabled:opacity-40"
            >
              ✓ Accept recommendation
            </button>
          )}
          <button
            type="button"
            disabled={!actorReady || submitting}
            onClick={() => {
              setOverrideOpen(true);
              setOverrideChoice(opposite);
              setError(null);
            }}
            className="rounded-lg border-2 border-warn px-4 py-2 text-sm font-semibold text-warn transition hover:bg-warn/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            ⚠ Override
          </button>
        </div>
      )}

      {overrideOpen && (
        <div className="mt-1 space-y-3 border-t border-warn/30 pt-3">
          <p className="text-xs text-slate-400">
            Overriding the agent is the unusual, accountable path — a written
            reason is required and recorded in the audit log.
          </p>

          {opposite === null && (
            <div className="flex gap-2">
              {(["approve", "reject"] as Recommendation[]).map((choice) => (
                <button
                  key={choice}
                  type="button"
                  onClick={() => setOverrideChoice(choice)}
                  className={
                    overrideChoice === choice
                      ? "rounded-lg border-2 border-warn bg-warn/20 px-3 py-1.5 text-sm font-semibold text-warn"
                      : "rounded-lg border-2 border-navy-600 px-3 py-1.5 text-sm text-slate-300"
                  }
                >
                  {choice === "approve" ? "Approve" : "Reject"}
                </button>
              ))}
            </div>
          )}

          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why are you overriding the agent's recommendation? (required)"
            rows={3}
            className="w-full rounded-lg border border-warn/40 bg-navy-800 p-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-warn focus:outline-none"
          />

          <div className="flex gap-3">
            <button
              type="button"
              disabled={
                !actorReady ||
                submitting ||
                !overrideChoice ||
                reason.trim().length === 0
              }
              onClick={() => overrideChoice && submit(overrideChoice, true)}
              className="rounded-lg bg-warn px-4 py-2 text-sm font-semibold text-navy-950 transition hover:bg-warn/80 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Submit override
            </button>
            <button
              type="button"
              onClick={() => {
                setOverrideOpen(false);
                setError(null);
                setReason("");
              }}
              className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
