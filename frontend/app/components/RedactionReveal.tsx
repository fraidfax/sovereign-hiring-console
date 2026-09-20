import type { ScrubbedSpan } from "../lib/types";

interface RedactionRevealProps {
  removedFields: string[];
  scrubbedSpans: ScrubbedSpan[];
}

export function RedactionReveal({
  removedFields,
  scrubbedSpans,
}: RedactionRevealProps) {
  const nothingToShow = removedFields.length === 0 && scrubbedSpans.length === 0;

  return (
    <details className="group rounded-lg border border-navy-600 bg-navy-800/60">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-sm font-medium text-slate-200">
        <span aria-hidden className="text-accent transition group-open:rotate-90">
          ▸
        </span>
        <span>PII redaction — before / after</span>
        <span className="ml-auto rounded-full bg-navy-700 px-2 py-0.5 text-xs text-slate-400">
          {removedFields.length} field{removedFields.length === 1 ? "" : "s"}{" "}
          removed
        </span>
      </summary>

      <div className="space-y-3 border-t border-navy-600 px-3 py-3 text-sm">
        {nothingToShow && (
          <p className="text-slate-500">
            No redaction was necessary for this candidate.
          </p>
        )}

        {removedFields.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Fields stripped before scoring
            </p>
            <ul className="flex flex-wrap gap-x-3 gap-y-1">
              {removedFields.map((field) => (
                <li
                  key={field}
                  className="rounded bg-navy-700 px-2 py-0.5 text-slate-400 line-through decoration-red-400/70"
                >
                  {field}
                </li>
              ))}
            </ul>
          </div>
        )}

        {scrubbedSpans.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Free-text scrubbing
            </p>
            <ul className="space-y-1.5">
              {scrubbedSpans.map((span, i) => (
                <li key={`${span.field}-${i}`} className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-navy-700 px-1.5 py-0.5 font-mono text-[11px] text-slate-500">
                    {span.field}
                  </span>
                  <span className="text-red-300 line-through">
                    {span.original}
                  </span>
                  <span aria-hidden className="text-slate-500">
                    →
                  </span>
                  <span className="text-accent-bright">{span.replacement}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </details>
  );
}
