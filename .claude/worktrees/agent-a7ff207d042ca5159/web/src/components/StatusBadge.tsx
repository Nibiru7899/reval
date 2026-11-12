import type { Status } from "../api/client";
import { STATUS } from "../lib/status";

interface Props {
  status: Status;
  /** "chip" for tables, "glyph" for compact history cells (the label then goes to assistive tech and a tooltip). */
  variant?: "chip" | "glyph";
  className?: string;
}

/** A claim status: always an icon shape plus a text label, never colour alone. */
export function StatusBadge({ status, variant = "chip", className }: Props) {
  const meta = STATUS[status];
  const Icon = meta.icon;
  if (variant === "glyph") {
    return (
      <span className={`st-glyph st-${status} ${className ?? ""}`} title={meta.label} role="img" aria-label={meta.label}>
        <Icon size={13} strokeWidth={2} aria-hidden="true" />
      </span>
    );
  }
  return (
    <span className={`st-chip st-${status} ${className ?? ""}`} title={meta.hint}>
      <Icon size={14} strokeWidth={2} aria-hidden="true" />
      <span>{meta.label}</span>
    </span>
  );
}
