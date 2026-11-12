import type { Assessment, Criticality, Reason, Snapshot, Status } from "../api/client";
import { CRITICALITY_RANK, STATUS, STATUS_ORDER, formatLimit } from "./status";

export interface BoardRow {
  id: string;
  status: Status;
  reasons: Reason[];
  topReason: Reason | undefined;
  requirementId: string;
  requirementText: string;
  limit: string;
  criticality: Criticality | undefined;
  subjectId: string;
  subjectKind: string | undefined;
  evidenceCount: number;
  /** Status at each recent snapshot, oldest first; undefined where the claim was not assessed. */
  history: (Status | undefined)[];
}

export type SortKey = "claim" | "subject" | "requirement" | "status" | "reason" | "criticality";
export interface Sort {
  key: SortKey;
  dir: "asc" | "desc";
}

export interface Filters {
  text: string;
  requirement: string; // "" = all
  criticality: Criticality | "";
  statuses: ReadonlySet<Status>;
}

export const NO_FILTERS: Filters = { text: "", requirement: "", criticality: "", statuses: new Set() };

/** Joins assessments with the snapshot's claim, requirement and subject records. */
export function buildRows(
  assessments: Assessment[],
  snapshot: Pick<Snapshot, "claims" | "requirements" | "subjects"> | undefined,
  history: (Map<string, Status> | undefined)[] = [],
): BoardRow[] {
  return assessments.map((a) => {
    const claim = snapshot?.claims[a.claim_id];
    const req = claim ? snapshot?.requirements[claim.requirement_id] : undefined;
    const subj = claim ? snapshot?.subjects[claim.subject_id] : undefined;
    return {
      id: a.claim_id,
      status: a.status,
      reasons: [...a.reasons],
      topReason: a.reasons[0],
      requirementId: claim?.requirement_id ?? "",
      requirementText: req?.text ?? "",
      limit: req ? formatLimit(req.op, req.limit, req.unit) : "",
      criticality: req?.criticality,
      subjectId: claim?.subject_id ?? "",
      subjectKind: subj?.kind,
      evidenceCount: a.evidence.length,
      history: history.map((h) => h?.get(a.claim_id)),
    };
  });
}

export function countByStatus(rows: BoardRow[]): Record<Status, number> {
  const counts = Object.fromEntries(STATUS_ORDER.map((s) => [s, 0])) as Record<Status, number>;
  for (const r of rows) counts[r.status] += 1;
  return counts;
}

export function needsRevalidation(rows: BoardRow[]): number {
  return rows.filter((r) => !STATUS[r.status].accepted).length;
}

export function applyFilters(rows: BoardRow[], f: Filters): BoardRow[] {
  const q = f.text.trim().toLowerCase();
  return rows.filter(
    (r) =>
      (f.statuses.size === 0 || f.statuses.has(r.status)) &&
      (f.requirement === "" || r.requirementId === f.requirement) &&
      (f.criticality === "" || r.criticality === f.criticality) &&
      (q === "" ||
        [r.id, r.subjectId, r.requirementId, r.requirementText, r.topReason?.code ?? "", r.topReason?.message ?? ""]
          .join(" ")
          .toLowerCase()
          .includes(q)),
  );
}

const cmpStr = (a: string, b: string) => a.localeCompare(b, undefined, { numeric: true });

function compare(a: BoardRow, b: BoardRow, key: SortKey): number {
  switch (key) {
    case "claim":
      return cmpStr(a.id, b.id);
    case "subject":
      return cmpStr(a.subjectId, b.subjectId);
    case "requirement":
      return cmpStr(a.requirementId, b.requirementId);
    case "status":
      return STATUS[a.status].rank - STATUS[b.status].rank;
    case "reason":
      return cmpStr(a.topReason?.code ?? "~", b.topReason?.code ?? "~");
    case "criticality":
      return (
        (a.criticality ? CRITICALITY_RANK[a.criticality] : 9) - (b.criticality ? CRITICALITY_RANK[b.criticality] : 9)
      );
  }
}

/** Stable sort; ties fall back to attention order (status, criticality) and then claim id. */
export function sortRows(rows: BoardRow[], s: Sort): BoardRow[] {
  const sign = s.dir === "asc" ? 1 : -1;
  return [...rows].sort(
    (a, b) =>
      sign * compare(a, b, s.key) ||
      compare(a, b, "status") ||
      compare(a, b, "criticality") ||
      compare(a, b, "claim"),
  );
}
