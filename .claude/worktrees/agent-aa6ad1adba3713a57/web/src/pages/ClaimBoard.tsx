import { ArrowDown, ArrowUp, ArrowUpDown, FilterX, RotateCw, Search, SearchX, Unplug } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useSearchParams } from "react-router-dom";
import type { Criticality, Status } from "../api/client";
import { useClaimHistory, useClaims, useSnapshot, useSnapshots } from "../api/queries";
import { ClaimDrawer } from "../components/ClaimDrawer";
import { CriticalityMark } from "../components/CriticalityMark";
import { StatusBadge } from "../components/StatusBadge";
import { StatusRuler } from "../components/StatusRuler";
import {
  applyFilters,
  buildRows,
  countByStatus,
  needsRevalidation,
  NO_FILTERS,
  sortRows,
  type BoardRow,
  type Filters,
  type Sort,
  type SortKey,
} from "../lib/board";
import { CRITICALITY_ORDER, humanize, shortHash } from "../lib/status";
import { useSnapshotParam } from "../lib/useSnapshotParam";

const HISTORY_DEPTH = 5;

const COLUMNS: { key: SortKey; label: string; className: string }[] = [
  { key: "claim", label: "Claim", className: "col-claim" },
  { key: "subject", label: "Subject", className: "col-subject" },
  { key: "requirement", label: "Requirement", className: "col-req" },
  { key: "status", label: "Status", className: "col-status" },
  { key: "reason", label: "Top reason", className: "col-reason" },
  { key: "criticality", label: "Criticality", className: "col-crit" },
];

function revLabel(s: { id: string; git_rev?: string | null } | undefined): string {
  if (!s) return "";
  return s.git_rev ? shortHash(s.git_rev, 7) : shortHash(s.id);
}

export function ClaimBoard() {
  const [snapshotParam] = useSnapshotParam();
  const [params, setParams] = useSearchParams();
  const claims = useClaims(snapshotParam);
  const snapshots = useSnapshots();
  const snapshotId = claims.data?.[0]?.snapshot_id;
  const snapshot = useSnapshot(snapshotId);

  // Recent snapshots up to and including the shown one, oldest first, for the history column.
  const recent = useMemo(() => {
    const list = snapshots.data ?? [];
    const at = snapshotId ? list.findIndex((s) => s.id === snapshotId) : 0;
    const from = at < 0 ? 0 : at;
    return list.slice(from, from + HISTORY_DEPTH).reverse();
  }, [snapshots.data, snapshotId]);
  const previous = recent.length > 1 ? recent[recent.length - 2] : undefined;
  // History waits for the snapshot detail: the API serialises requests and the columns need the detail first.
  const history = useClaimHistory(recent.length > 1 ? recent.map((s) => s.id) : [], snapshot.isSuccess);
  const historyKey = history.map((q) => q.dataUpdatedAt).join(",");
  const historyMaps = useMemo(
    () => history.map((q) => (q.data ? new Map(q.data.map((a) => [a.claim_id, a.status] as const)) : undefined)),
    // The query array identity changes every render; its data timestamps are the real dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [historyKey],
  );

  const rows = useMemo(
    () => buildRows(claims.data ?? [], snapshot.data, recent.length > 1 ? historyMaps : []),
    [claims.data, snapshot.data, historyMaps, recent.length],
  );

  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [sort, setSort] = useState<Sort>({ key: "status", dir: "asc" });
  const shown = useMemo(() => sortRows(applyFilters(rows, filters), sort), [rows, filters, sort]);
  const counts = useMemo(() => countByStatus(rows), [rows]);
  const pending = needsRevalidation(rows);
  const filtering =
    filters.text !== "" || filters.requirement !== "" || filters.criticality !== "" || filters.statuses.size > 0;

  const requirements = useMemo(() => {
    const reqs = snapshot.data?.requirements ?? {};
    return Object.values(reqs).sort((a, b) => a.id.localeCompare(b.id));
  }, [snapshot.data]);

  // Selection (drawer) is in the URL so a claim can be linked to.
  const selectedId = params.get("claim") ?? undefined;
  const selected = rows.find((r) => r.id === selectedId);
  const openClaim = useCallback(
    (id: string | undefined) =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (id === undefined) next.delete("claim");
          else next.set("claim", id);
          return next;
        },
        { replace: true },
      ),
    [setParams],
  );

  // Roving focus over table rows.
  const [cursor, setCursor] = useState(0);
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);
  const searchRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (cursor >= shown.length) setCursor(Math.max(0, shown.length - 1));
  }, [shown.length, cursor]);

  const focusRow = (i: number) => {
    const n = Math.max(0, Math.min(shown.length - 1, i));
    setCursor(n);
    rowRefs.current[n]?.focus();
  };

  const closeDrawer = () => {
    openClaim(undefined);
    rowRefs.current[cursor]?.focus();
  };

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = t !== null && (t.tagName === "INPUT" || t.tagName === "SELECT" || t.tagName === "TEXTAREA");
      if (e.key === "/" && !typing) {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const onTableKey = (e: KeyboardEvent<HTMLTableSectionElement>) => {
    const key = e.key;
    if (key === "ArrowDown" || key === "j") focusRow(cursor + 1);
    else if (key === "ArrowUp" || key === "k") focusRow(cursor - 1);
    else if (key === "Home") focusRow(0);
    else if (key === "End") focusRow(shown.length - 1);
    else if (key === "PageDown") focusRow(cursor + 10);
    else if (key === "PageUp") focusRow(cursor - 10);
    else if (key === "Enter" || key === " ") {
      const r = shown[cursor];
      if (r) openClaim(r.id);
    } else if (key === "Escape" && selected) closeDrawer();
    else return;
    e.preventDefault();
  };

  const toggleStatus = (s: Status) =>
    setFilters((f) => {
      const next = new Set(f.statuses);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return { ...f, statuses: next };
    });

  const onSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" }));

  const shownRev = revLabel(snapshot.data ?? (snapshotId ? { id: snapshotId } : undefined));
  const baseline = previous ? revLabel(previous) : shownRev;

  return (
    <div className={`page board${selected ? " has-drawer" : ""}`}>
      <div className="board-main">
        <header className="page-head">
          <h1>Claim board</h1>
          {snapshotId && (
            <p className="page-ref mono">
              <span className="sr-only">Assessed snapshot </span>
              <span title={snapshotId}>{shortHash(snapshotId, 12)}</span>
              <span className="sep" aria-hidden="true">
                /
              </span>
              <span>{snapshot.data?.git_rev ? `rev ${shortHash(snapshot.data.git_rev, 7)}` : "working tree"}</span>
            </p>
          )}
        </header>

        {claims.isError ? (
          <ErrorState message={claims.error.message} onRetry={() => void claims.refetch()} />
        ) : claims.isLoading ? (
          <LoadingState />
        ) : rows.length === 0 ? (
          <div className="state-block">
            <SearchX size={28} strokeWidth={1.25} aria-hidden="true" />
            <p className="state-title">No claims declared</p>
            <p className="state-body">
              The project manifest (<code>reval.yaml</code>) declares no claims yet, so there is nothing to assess.
            </p>
          </div>
        ) : (
          <>
            <p className="headline" aria-live="polite">
              {pending === 0 ? (
                <>
                  No claims need revalidation {previous ? "since" : "at"} <span className="mono">{baseline}</span>
                </>
              ) : (
                <>
                  <strong className="num">{pending}</strong> of <span className="num">{rows.length}</span> claims need
                  revalidation {previous ? "since" : "at"} <span className="mono">{baseline}</span>
                </>
              )}
            </p>

            <StatusRuler counts={counts} active={filters.statuses} onToggle={toggleStatus} />

            <div className="filters" role="search" aria-label="Filter claims">
              <label className="field field-search">
                <Search size={15} strokeWidth={1.75} aria-hidden="true" />
                <span className="sr-only">Search claims</span>
                <input
                  ref={searchRef}
                  type="search"
                  placeholder="Search claim, subject, requirement, reason"
                  value={filters.text}
                  onChange={(e) => setFilters((f) => ({ ...f, text: e.target.value }))}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      focusRow(0);
                    }
                  }}
                />
                <kbd aria-hidden="true">/</kbd>
              </label>
              <label className="field">
                <span className="field-label">Requirement</span>
                <select
                  value={filters.requirement}
                  onChange={(e) => setFilters((f) => ({ ...f, requirement: e.target.value }))}
                >
                  <option value="">All</option>
                  {requirements.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.id}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span className="field-label">Criticality</span>
                <select
                  value={filters.criticality}
                  onChange={(e) => setFilters((f) => ({ ...f, criticality: e.target.value as Criticality | "" }))}
                >
                  <option value="">All</option>
                  {CRITICALITY_ORDER.map((c) => (
                    <option key={c} value={c}>
                      {humanize(c)}
                    </option>
                  ))}
                </select>
              </label>
              <p className="filters-count" aria-live="polite">
                <span className="num">{shown.length}</span> of <span className="num">{rows.length}</span> shown
              </p>
              {filtering && (
                <button type="button" className="btn-quiet" onClick={() => setFilters(NO_FILTERS)}>
                  <FilterX size={14} strokeWidth={1.75} aria-hidden="true" />
                  Clear filters
                </button>
              )}
            </div>

            {shown.length === 0 ? (
              <div className="state-block">
                <SearchX size={28} strokeWidth={1.25} aria-hidden="true" />
                <p className="state-title">No claims match these filters</p>
                <button type="button" className="btn" onClick={() => setFilters(NO_FILTERS)}>
                  Clear filters
                </button>
              </div>
            ) : (
              <div className="table-wrap">
                <table className="claims" aria-label="Claims" aria-rowcount={shown.length + 1}>
                  <thead>
                    <tr aria-rowindex={1}>
                      {COLUMNS.map((c) => {
                        const active = sort.key === c.key;
                        const Icon = !active ? ArrowUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
                        return (
                          <th
                            key={c.key}
                            scope="col"
                            className={c.className}
                            aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
                          >
                            <button type="button" className="th-sort" onClick={() => onSort(c.key)}>
                              {c.label}
                              <Icon size={12} strokeWidth={2} aria-hidden="true" className={active ? "" : "faint"} />
                            </button>
                          </th>
                        );
                      })}
                      {recent.length > 1 && (
                        <th scope="col" className="col-hist">
                          <span className="th-static" title="Status at the most recent snapshots, oldest to newest">
                            Recent
                          </span>
                        </th>
                      )}
                    </tr>
                  </thead>
                  <tbody onKeyDown={onTableKey}>
                    {shown.map((r, i) => (
                      <ClaimRow
                        key={r.id}
                        row={r}
                        index={i}
                        focusable={i === cursor}
                        metaPending={snapshot.isPending}
                        selected={r.id === selectedId}
                        recent={recent.length > 1 ? recent.map(revLabel) : []}
                        rowRef={(el) => {
                          rowRefs.current[i] = el;
                        }}
                        onOpen={() => {
                          setCursor(i);
                          openClaim(r.id);
                        }}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="kbd-hint">
              <kbd>↑</kbd>
              <kbd>↓</kbd> move <span aria-hidden="true">·</span> <kbd>Enter</kbd> open{" "}
              <span aria-hidden="true">·</span> <kbd>Esc</kbd> close <span aria-hidden="true">·</span> <kbd>/</kbd>{" "}
              search
            </p>
          </>
        )}
      </div>
      {selected && (
        <ClaimDrawer
          row={selected}
          snapshotId={snapshotId}
          gitRev={snapshot.data?.git_rev}
          metaPending={snapshot.isPending}
          onClose={closeDrawer}
        />
      )}
    </div>
  );
}

interface RowProps {
  row: BoardRow;
  index: number;
  focusable: boolean;
  metaPending: boolean;
  selected: boolean;
  recent: string[];
  rowRef: (el: HTMLTableRowElement | null) => void;
  onOpen: () => void;
}

function ClaimRow({ row, index, focusable, metaPending, selected, recent, rowRef, onOpen }: RowProps) {
  const pending = <span className="skel skel-cell" aria-label="Loading" role="img" />;
  return (
    <tr
      ref={rowRef}
      tabIndex={focusable ? 0 : -1}
      aria-rowindex={index + 2}
      aria-selected={selected}
      className={selected ? "is-selected" : undefined}
      onClick={onOpen}
    >
      <td className="col-claim">
        <span className="mono strong">{row.id}</span>
      </td>
      <td className="col-subject">
        {row.subjectId ? <span className="mono">{row.subjectId}</span> : metaPending ? pending : "—"}
      </td>
      <td className="col-req" title={row.requirementText}>
        {row.requirementId ? <span className="mono">{row.requirementId}</span> : metaPending ? pending : "—"}
        {row.limit && <span className="req-limit num">{row.limit}</span>}
      </td>
      <td className="col-status">
        <StatusBadge status={row.status} />
      </td>
      <td className="col-reason" title={row.topReason?.message}>
        {row.topReason ? (
          <>
            <span className="reason-head">{humanize(row.topReason.code)}</span>
            <span className="reason-tail">{row.topReason.message}</span>
          </>
        ) : (
          <span className="muted">—</span>
        )}
      </td>
      <td className="col-crit">
        {row.criticality ? <CriticalityMark value={row.criticality} /> : metaPending ? pending : "—"}
      </td>
      {recent.length > 0 && (
        <td className="col-hist">
          <span className="hist">
            {row.history.map((s, i) =>
              s ? (
                <span key={i} className="hist-cell" title={`${recent[i] ?? ""}`}>
                  <StatusBadge status={s} variant="glyph" />
                </span>
              ) : (
                <span key={i} className="hist-cell hist-none" role="img" aria-label="Not assessed" title="Not assessed">
                  ·
                </span>
              ),
            )}
          </span>
        </td>
      )}
    </tr>
  );
}

function LoadingState() {
  return (
    <div className="loading" role="status" aria-label="Loading claims">
      <div className="skel skel-headline" />
      <div className="skel skel-ruler" />
      <div className="skel-table">
        {Array.from({ length: 9 }, (_, i) => (
          <div key={i} className="skel skel-row" style={{ animationDelay: `${i * 60}ms` }} />
        ))}
      </div>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="state-block state-error" role="alert">
      <Unplug size={28} strokeWidth={1.25} aria-hidden="true" />
      <p className="state-title">Could not load claims</p>
      <p className="state-body">
        The API answered <span className="mono">{message}</span>. Check that{" "}
        <code>reval serve --project &lt;path&gt;</code> is running.
      </p>
      <button type="button" className="btn" onClick={onRetry}>
        <RotateCw size={14} strokeWidth={1.75} aria-hidden="true" />
        Try again
      </button>
    </div>
  );
}
