---
version: 1
slug: "src-pages-claimboard-tsx"
primary_target: "src/pages/ClaimBoard.tsx"
related_targets: ["src/App.tsx"]
---

# Surface brief: Claim board (and app shell)

Scope: the ReVal workspace shell plus its first page, the Claim board. Mode: Operate.
Audience: design/test engineers checking which claims a change put at risk. Task: scan statuses, filter by
requirement / criticality / status / text, open a claim. Content: assessments from `/api/v1` (motor_thermal).
Constraints: status never by colour alone; honest language; dense, calm, precise; light + dark.

Answer channel: none in this orchestrated run; the decision round was inferred from the owner's brief.
Grounded list (ordered): 1 component datasheet, 2 drawing title block + revision table, 3 QC hold/pass tags,
4 quad-ruled lab notebook, 5 motor rating plate, 6 DIN/ISO standards publication, 7 IEC wire colour codes.
Challenger verdicts: emission rail declined (kept: state carried in form, not hue); timetable rack declined
(kept: one table size, rank by weight/case); ticket wallet declined; warm consumer declined; Crouwel grid
declined; terminal yellow declined (kept: one message per headline line).

## Direction contract

THESIS: The workspace reads like a well-set standards publication: numbered, ruled, referenced, unhurried. It refuses the
SaaS dashboard of KPI cards and pastel badges.
OWN-WORLD: Cool paper ground with a deep slate-teal "cover" rail; black ink, DIN-lineage grotesk (Barlow, Barlow
Semi Condensed for column heads in caps) with JetBrains Mono only for hashes, ids and numbers; hairline rules, 2-4px
radii, Okabe-Ito status inks each paired with a distinct icon shape and a hatch pattern.
STORY: The engineer sees the one-line verdict ("N claims need revalidation since <rev>"), the population of statuses,
then the rows that need them, and opens one.
FIRST VIEWPORT: Left rail (brand, 5 nav items, project). Header: project name, snapshot short hash + git rev. Headline
sentence, then the status ruler, then filters, then the dense table filling the rest; drawer slides from the right.
FORM: Candidate 6 (DIN/ISO standards publication), seed eddabc9c. Signature move: the status ruler, a proportional,
hatched, ticked scale of the claim population whose segments are the status filter.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
