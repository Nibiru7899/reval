import type { Status } from "../api/client";
import { STATUS, STATUS_ORDER } from "../lib/status";

interface Props {
  counts: Record<Status, number>;
  active: ReadonlySet<Status>;
  onToggle: (s: Status) => void;
}

const TICKS = [0, 25, 50, 75, 100];

/**
 * The claim population as one proportional, ticked scale. Each status has its own ink, hatch and icon,
 * and the legend entries below double as the status filter.
 */
export function StatusRuler({ counts, active, onToggle }: Props) {
  const total = STATUS_ORDER.reduce((n, s) => n + counts[s], 0);
  const filtering = active.size > 0;
  return (
    <section className="ruler" aria-label="Claims by status">
      <div className="ruler-bar" aria-hidden="true">
        {total === 0 ? (
          <span className="ruler-empty" />
        ) : (
          STATUS_ORDER.filter((s) => counts[s] > 0).map((s) => (
            <span
              key={s}
              className={`ruler-seg st-${s}${filtering && !active.has(s) ? " is-dim" : ""}`}
              style={{ flexGrow: counts[s] }}
              onClick={() => onToggle(s)}
            >
              <span className="ruler-seg-n">{counts[s]}</span>
            </span>
          ))
        )}
      </div>
      <div className="ruler-scale" aria-hidden="true">
        {TICKS.map((t) => (
          <span key={t} className="ruler-tick" style={{ left: `${t}%` }}>
            <span>{t}%</span>
          </span>
        ))}
      </div>
      <ul className="ruler-legend" role="list">
        {STATUS_ORDER.map((s) => {
          const meta = STATUS[s];
          const Icon = meta.icon;
          const n = counts[s];
          const pct = total === 0 ? 0 : Math.round((n / total) * 100);
          const pressed = active.has(s);
          return (
            <li key={s}>
              <button
                type="button"
                className={`ruler-key st-${s}${pressed ? " is-on" : ""}`}
                aria-pressed={pressed}
                disabled={n === 0 && !pressed}
                onClick={() => onToggle(s)}
                title={`${meta.hint}. ${pressed ? "Click to remove this filter" : "Click to show only these"}`}
              >
                <span className="ruler-key-swatch" aria-hidden="true">
                  <Icon size={14} strokeWidth={2} />
                </span>
                <span className="ruler-key-label">{meta.label}</span>{" "}
                <span className="ruler-key-n">{n}</span>{" "}
                <span className="ruler-key-pct">{pct}%</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
