import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import type { BoardRow } from "../lib/board";
import { humanize, shortHash } from "../lib/status";
import { CriticalityMark } from "./CriticalityMark";
import { StatusBadge } from "./StatusBadge";

interface Props {
  row: BoardRow;
  snapshotId: string | undefined;
  gitRev: string | null | undefined;
  metaPending?: boolean;
  onClose: () => void;
}

/**
 * Claim detail drawer. This is the stub the claim board opens; the claim detail task adds the
 * justification tree, the envelope plot and the interval-vs-limit chart in the marked section.
 */
export function ClaimDrawer({ row, snapshotId, gitRev, metaPending = false, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
  }, [row.id]);
  const titleId = `drawer-title-${row.id}`;
  return (
    <div
      className="drawer"
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
        }
      }}
    >
      <header className="drawer-head">
        <div>
          <h2 id={titleId} className="drawer-title">
            {row.id}
          </h2>
          <p className="drawer-sub">{row.requirementText || (metaPending ? "Loading requirement…" : "Requirement text unavailable")}</p>
        </div>
        <button ref={closeRef} type="button" className="icon-btn" onClick={onClose} aria-label="Close claim detail">
          <X size={18} strokeWidth={1.75} aria-hidden="true" />
        </button>
      </header>

      <dl className="facts">
        <div>
          <dt>Status</dt>
          <dd>
            <StatusBadge status={row.status} />
          </dd>
        </div>
        <div>
          <dt>Requirement</dt>
          <dd>
            <span className="mono">{row.requirementId}</span> <span className="muted">{row.limit}</span>
          </dd>
        </div>
        <div>
          <dt>Criticality</dt>
          <dd>{row.criticality ? <CriticalityMark value={row.criticality} /> : "—"}</dd>
        </div>
        <div>
          <dt>Subject</dt>
          <dd>
            <span className="mono">{row.subjectId}</span>
            {row.subjectKind && <span className="muted"> {humanize(row.subjectKind).toLowerCase()}</span>}
          </dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd className="num">{row.evidenceCount} item{row.evidenceCount === 1 ? "" : "s"}</dd>
        </div>
        <div>
          <dt>Snapshot</dt>
          <dd className="mono">
            {snapshotId ? shortHash(snapshotId, 12) : "—"}
            <span className="muted"> · {gitRev ? shortHash(gitRev, 7) : "working tree"}</span>
          </dd>
        </div>
      </dl>

      <section className="drawer-section" aria-labelledby={`${titleId}-reasons`}>
        <h3 id={`${titleId}-reasons`}>Reasons</h3>
        {row.reasons.length === 0 ? (
          <p className="muted">No reasons recorded.</p>
        ) : (
          <ol className="reasons">
            {row.reasons.map((r, i) => (
              <li key={`${r.code}-${i}`}>
                <span className="reason-code mono">{r.code}</span>
                <span className="reason-msg">{r.message}</span>
                {r.evidence_ids && r.evidence_ids.length > 0 && (
                  <span className="reason-ev mono">
                    {r.evidence_ids.map((e) => shortHash(e)).join(" · ")}
                  </span>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="drawer-section drawer-pending" aria-label="Justification and plots">
        <h3>Justification</h3>
        <p className="muted">
          The justification tree, envelope plot and interval-vs-limit chart for this claim will appear here. Until then,{" "}
          <code>reval explain {row.id}</code> prints the same justification in the terminal.
        </p>
      </section>
    </div>
  );
}
