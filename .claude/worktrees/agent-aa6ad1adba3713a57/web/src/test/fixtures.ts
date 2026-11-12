import createClient from "openapi-fetch";
import type { ApiClient, Assessment, Snapshot, SnapshotSummary } from "../api/client";
import type { paths } from "../api/schema";

const S1 = "a".repeat(64);
const S0 = "b".repeat(64);

function assessment(claim_id: string, status: Assessment["status"], code: string, message: string, snapshot_id = S1): Assessment {
  return {
    claim_id,
    snapshot_id,
    status,
    reasons: [{ code: code as Assessment["reasons"][number]["code"], message, evidence_ids: [], detail: {} }],
    evidence: [],
    satisfied_clause: null,
    input_hash: "h".repeat(64),
  };
}

export const CLAIMS: Assessment[] = [
  assessment("C-P01-PM", "violated", "requirement_violated", "magnet peak 94.1 °C exceeds 90 °C"),
  assessment("C-P01-SW", "supported", "policy_satisfied", "clause 0 satisfied"),
  assessment("C-P02-PM", "stale", "evidence_invalidated", "supporting evidence lost freshness"),
  assessment("C-P02-SW", "inconclusive", "no_evidence", "no eligible evidence for claim C-P02-SW"),
  assessment("C-P03-IS", "waived", "waiver_applied", "waiver W-7 applied"),
];

export const HISTORY: Assessment[] = [
  assessment("C-P01-PM", "supported", "policy_satisfied", "ok", S0),
  assessment("C-P01-SW", "supported", "policy_satisfied", "ok", S0),
];

export const SNAPSHOTS: SnapshotSummary[] = [
  { id: S1, git_rev: "1234567890abcdef", claims: 5 },
  { id: S0, git_rev: "a1b2c3d4e5f6", claims: 5 },
];

const req = (id: string, text: string, quantity: string, limit: number, unit: string, criticality: "low" | "medium" | "high") => ({
  id,
  text,
  quantity,
  op: "<=" as const,
  limit,
  unit,
  criticality,
});

export const SNAPSHOT = {
  id: S1,
  git_rev: "1234567890abcdef",
  manifest_hash: "m",
  quantities: {},
  artifacts: {},
  versions: {},
  assumptions: {},
  policies: {},
  producers: {},
  requirements: {
    "R-PM-MAX": req("R-PM-MAX", "Magnet temperature stays at or below the declared study limit", "pm_peak", 90, "degC", "high"),
    "R-SW-MAX": req("R-SW-MAX", "Stator winding temperature stays at or below the limit", "sw_peak", 130, "degC", "medium"),
    "R-IS-MAX": req("R-IS-MAX", "Peak stator current stays at or below the inverter limit", "is_peak", 315, "A", "low"),
  },
  subjects: {
    "DC-P01": { id: "DC-P01", kind: "duty_cycle", generator: null, params: {} },
    "DC-P02": { id: "DC-P02", kind: "duty_cycle", generator: null, params: {} },
    "DC-P03": { id: "DC-P03", kind: "duty_cycle", generator: null, params: {} },
  },
  claims: {
    "C-P01-PM": { id: "C-P01-PM", requirement_id: "R-PM-MAX", subject_id: "DC-P01", policy_id: null },
    "C-P01-SW": { id: "C-P01-SW", requirement_id: "R-SW-MAX", subject_id: "DC-P01", policy_id: null },
    "C-P02-PM": { id: "C-P02-PM", requirement_id: "R-PM-MAX", subject_id: "DC-P02", policy_id: null },
    "C-P02-SW": { id: "C-P02-SW", requirement_id: "R-SW-MAX", subject_id: "DC-P02", policy_id: null },
    "C-P03-IS": { id: "C-P03-IS", requirement_id: "R-IS-MAX", subject_id: "DC-P03", policy_id: null },
  },
} as unknown as Snapshot;

type Route = (url: URL) => unknown;

export interface MockOptions {
  claims?: Assessment[];
  failClaims?: boolean;
  routes?: Record<string, Route>;
}

/** A generated-type client whose fetch answers from fixtures; no network. */
export function mockClient(opts: MockOptions = {}): ApiClient {
  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  const fetchFn = async (input: Request) => {
    const url = new URL(input.url);
    const path = url.pathname;
    if (path === "/api/v1/projects") return json([{ id: "default", name: "motor-thermal", claims: 5 }]);
    if (path === "/api/v1/projects/default/snapshots") return json(SNAPSHOTS);
    if (path.startsWith("/api/v1/projects/default/snapshots/")) return json(SNAPSHOT);
    if (path === "/api/v1/projects/default/claims") {
      if (opts.failClaims) return json({ detail: "unknown snapshot 'zzz'" }, 404);
      return json(url.searchParams.get("snapshot") === S0 ? HISTORY : (opts.claims ?? CLAIMS));
    }
    return json({ detail: "not found" }, 404);
  };
  return createClient<paths>({ baseUrl: "http://reval.test", fetch: fetchFn });
}
