import { GitCommitHorizontal, Network, Route as RouteIcon, FileText } from "lucide-react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ClaimBoard } from "./pages/ClaimBoard";
import { Placeholder } from "./pages/Placeholder";

function ToClaims() {
  const { search } = useLocation();
  return <Navigate to={{ pathname: "/claims", search }} replace />;
}

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<ToClaims />} />
        <Route path="/claims" element={<ClaimBoard />} />
        <Route
          path="/changes"
          element={
            <Placeholder title="Changes" icon={GitCommitHorizontal}>
              Snapshots with their change sets, and the claims each change reaches.
            </Placeholder>
          }
        />
        <Route
          path="/graph"
          element={
            <Placeholder title="Graph" icon={Network}>
              The evidence graph, collapsed to claims, with the influence cone of a selected node.
            </Placeholder>
          }
        />
        <Route
          path="/planner"
          element={
            <Placeholder title="Planner" icon={RouteIcon}>
              Revalidation obligations, a budget, and the lowest-cost set of runs that restores support.
            </Placeholder>
          }
        />
        <Route
          path="/reports"
          element={
            <Placeholder title="Reports" icon={FileText}>
              The decision-validity report with its hashes and disclaimer. Until then, run reval report --html.
            </Placeholder>
          }
        />
        <Route path="*" element={<ToClaims />} />
      </Routes>
    </AppShell>
  );
}
