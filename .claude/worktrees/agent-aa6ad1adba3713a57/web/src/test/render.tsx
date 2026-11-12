import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { ApiProvider } from "../api/ApiContext";
import type { ApiClient } from "../api/client";

export function renderWithApi(ui: ReactElement, client: ApiClient, path = "/claims") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ApiProvider client={client}>
        <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>,
  );
}
