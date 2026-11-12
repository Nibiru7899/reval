import { CircleCheck, CircleHelp, Hourglass, OctagonX, Stamp, type LucideIcon } from "lucide-react";
import type { Criticality, Status } from "../api/client";

export interface StatusMeta {
  label: string;
  icon: LucideIcon;
  /** One line, in the domain model's own words (docs/03-domain-model.md). */
  hint: string;
  /** Board order: what needs attention first. */
  rank: number;
  accepted: boolean;
}

export const STATUS: Record<Status, StatusMeta> = {
  violated: {
    label: "Violated",
    icon: OctagonX,
    hint: "Fresh evidence fails the requirement",
    rank: 0,
    accepted: false,
  },
  stale: {
    label: "Stale",
    icon: Hourglass,
    hint: "Evidence lost freshness after a change",
    rank: 1,
    accepted: false,
  },
  inconclusive: {
    label: "Inconclusive",
    icon: CircleHelp,
    hint: "Fresh evidence does not decide the requirement",
    rank: 2,
    accepted: false,
  },
  waived: {
    label: "Waived",
    icon: Stamp,
    hint: "Accepted under a recorded waiver",
    rank: 3,
    accepted: true,
  },
  supported: {
    label: "Supported",
    icon: CircleCheck,
    hint: "Supported by recorded evidence against the declared requirement",
    rank: 4,
    accepted: true,
  },
};

export const STATUS_ORDER: Status[] = (Object.keys(STATUS) as Status[]).sort((a, b) => STATUS[a].rank - STATUS[b].rank);

export const CRITICALITY_RANK: Record<Criticality, number> = { high: 0, medium: 1, low: 2 };
export const CRITICALITY_ORDER: Criticality[] = ["high", "medium", "low"];

/** Short, stable form of a content hash. */
export function shortHash(id: string, n = 8): string {
  return id.slice(0, n);
}

/** "≤ 120 °C"-style rendering of a requirement's comparator and limit. */
export function formatLimit(op: string, limit: number, unit: string): string {
  const sym = op === "<=" ? "≤" : op === ">=" ? "≥" : op;
  const value = Number.isInteger(limit) ? String(limit) : String(Number(limit.toPrecision(6)));
  const u = unit === "degC" ? "°C" : unit === "delta_degC" || unit === "K" ? "K" : unit;
  return `${sym} ${value}${u ? ` ${u}` : ""}`;
}

export function humanize(code: string): string {
  const s = code.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
