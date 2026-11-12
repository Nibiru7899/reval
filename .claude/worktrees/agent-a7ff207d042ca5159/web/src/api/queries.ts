import { useQueries, useQuery } from "@tanstack/react-query";
import { PROJECT, type Assessment } from "./client";
import { useApi } from "./ApiContext";

/** Turns an openapi-fetch result into a value or a thrown Error with the API's detail message. */
function unwrap<T>(res: { data?: T; error?: unknown; response: Response }): T {
  if (res.data !== undefined) return res.data;
  const detail =
    typeof res.error === "object" && res.error !== null && "detail" in res.error
      ? String((res.error as { detail: unknown }).detail)
      : `${res.response.status} ${res.response.statusText}`.trim();
  throw new Error(detail);
}

const p = { path: { p: PROJECT } } as const;

export function useProjects() {
  const api = useApi();
  return useQuery({
    queryKey: ["projects"],
    queryFn: async () => unwrap(await api.GET("/api/v1/projects")),
  });
}

export function useSnapshots() {
  const api = useApi();
  return useQuery({
    queryKey: ["snapshots"],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/projects/{p}/snapshots", { params: { ...p, query: { limit: 50 } } })),
  });
}

export function useSnapshot(id: string | undefined) {
  const api = useApi();
  return useQuery({
    queryKey: ["snapshot", id],
    enabled: id !== undefined,
    staleTime: Infinity, // snapshots are content-addressed: an id never changes meaning
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/projects/{p}/snapshots/{s}", { params: { path: { p: PROJECT, s: id ?? "" } } })),
  });
}

async function fetchClaims(api: ReturnType<typeof useApi>, snapshot: string | undefined): Promise<Assessment[]> {
  const query = snapshot === undefined ? { limit: 1000 } : { snapshot, limit: 1000 };
  return unwrap(await api.GET("/api/v1/projects/{p}/claims", { params: { ...p, query } }));
}

/** Latest assessment of every claim at `snapshot` (default: the latest assessed snapshot). */
export function useClaims(snapshot: string | undefined) {
  const api = useApi();
  return useQuery({ queryKey: ["claims", snapshot ?? "latest"], queryFn: () => fetchClaims(api, snapshot) });
}

/** Assessments at several snapshots, for the board's recent-history column. Failures stay per snapshot. */
export function useClaimHistory(snapshots: string[], enabled = true) {
  const api = useApi();
  return useQueries({
    queries: snapshots.map((s) => ({
      queryKey: ["claims", s],
      queryFn: () => fetchClaims(api, s),
      staleTime: 60_000,
      enabled,
    })),
  });
}
