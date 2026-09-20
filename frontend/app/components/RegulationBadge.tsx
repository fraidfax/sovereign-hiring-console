interface Regulation {
  code: string;
  gloss: string;
}

const REGULATIONS: Regulation[] = [
  {
    code: "EU AI Act — Article 6",
    gloss:
      "Classifies employment-related AI as high-risk, which triggers a legal duty for human oversight of its outputs.",
  },
  {
    code: "GDPR — Article 22",
    gloss:
      "Gives candidates the right not to be subject to a decision based solely on automated processing — a human must review it.",
  },
];

function RegulationBadge({ code, gloss }: Regulation) {
  return (
    <details className="group inline-block" title={gloss}>
      <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-full border border-accent/40 bg-accent-dim/10 px-3 py-1 text-xs font-semibold text-accent-bright">
        <span aria-hidden>§</span>
        {code}
      </summary>
      <p className="mt-1 max-w-xs rounded-lg border border-navy-600 bg-navy-800 p-2 text-xs font-normal text-slate-300">
        {gloss}
      </p>
    </details>
  );
}

export function RegulationBadges() {
  return (
    <div className="flex flex-wrap gap-2">
      {REGULATIONS.map((reg) => (
        <RegulationBadge key={reg.code} {...reg} />
      ))}
    </div>
  );
}
