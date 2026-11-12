import type { LucideIcon } from "lucide-react";

/** Pages that later Phase 6 tasks fill in; the shell and navigation are real now. */
export function Placeholder({ title, icon: Icon, children }: { title: string; icon: LucideIcon; children: string }) {
  return (
    <div className="page">
      <header className="page-head">
        <h1>{title}</h1>
      </header>
      <div className="state-block">
        <Icon size={28} strokeWidth={1.25} aria-hidden="true" />
        <p className="state-title">Not built yet</p>
        <p className="state-body">{children}</p>
      </div>
    </div>
  );
}
