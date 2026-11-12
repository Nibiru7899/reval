import type { Criticality } from "../api/client";

const BARS: Record<Criticality, number> = { low: 1, medium: 2, high: 3 };
const LABEL: Record<Criticality, string> = { low: "Low", medium: "Medium", high: "High" };

/** Criticality as a three-step bar gauge plus its word, so the rank reads without colour. */
export function CriticalityMark({ value }: { value: Criticality }) {
  const n = BARS[value];
  return (
    <span className={`crit crit-${value}`}>
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <rect key={i} x={i * 4.2} y={8 - i * 3} width="3" height={4 + i * 3} rx="0.6" className={i < n ? "on" : "off"} />
        ))}
      </svg>
      {LABEL[value]}
    </span>
  );
}
