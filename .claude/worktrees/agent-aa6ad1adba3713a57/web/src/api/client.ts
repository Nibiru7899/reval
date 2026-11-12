import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

/** Generated-type client for `/api/v1` (types come from `npm run gen:api`; never hand-write them). */
export type ApiClient = ReturnType<typeof createClient<paths>>;

export function makeClient(baseUrl = ""): ApiClient {
  return createClient<paths>({ baseUrl });
}

export const PROJECT = "default";

export type Schemas = components["schemas"];
export type Assessment = Schemas["Assessment"];
export type Snapshot = Schemas["Snapshot"];
export type SnapshotSummary = Schemas["SnapshotSummary"];
export type ProjectInfo = Schemas["ProjectInfo"];
export type Status = Schemas["Status"];
export type Criticality = Schemas["Criticality"];
export type Requirement = Schemas["Requirement"];
export type Claim = Schemas["Claim"];
export type Reason = Schemas["Reason"];
