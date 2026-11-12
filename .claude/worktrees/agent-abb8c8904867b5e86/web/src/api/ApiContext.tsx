import { createContext, useContext, type ReactNode } from "react";
import { makeClient, type ApiClient } from "./client";

const ApiContext = createContext<ApiClient | null>(null);

/** Tests inject a mocked client here; the app uses the same-origin client. */
export function ApiProvider({ client, children }: { client?: ApiClient; children: ReactNode }) {
  return <ApiContext.Provider value={client ?? makeClient()}>{children}</ApiContext.Provider>;
}

export function useApi(): ApiClient {
  const c = useContext(ApiContext);
  if (c === null) throw new Error("useApi needs <ApiProvider>");
  return c;
}
