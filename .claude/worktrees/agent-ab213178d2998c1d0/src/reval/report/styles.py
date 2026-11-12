# ruff: noqa: E501  (inline HTML/CSS/SVG string literals)
"""Inline stylesheet and icon sprite for the HTML report. Self-contained: system fonts, no external assets.

Design notes: a printed engineering report first (paper tone, serif headings, tabular figures); every status
is an icon shape plus a word, and colour only reinforces it. Dark mode follows the reader's system setting.
"""

CSS = """
:root {
  color-scheme: light dark;
  --bg: #f5f2ea; --surface: #fffdf8; --ink: #1c2024; --muted: #565d65; --rule: #d6d0c1; --rule-soft: #e6e1d4;
  --ok-fg: #1b6537; --ok-bg: #e0f0e4;
  --waived-fg: #1d5584; --waived-bg: #dfeaf5;
  --stale-fg: #774700; --stale-bg: #f6e8c4;
  --inc-fg: #55438a; --inc-bg: #eae5f5;
  --bad-fg: #9e1f1a; --bad-bg: #f8dfdb;
  --limit: #1c2024; --track: #e9e4d6;
  --serif: "Iowan Old Style", "Palatino Linotype", Charter, Georgia, serif;
  --sans: ui-sans-serif, system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, "Cascadia Mono", "SF Mono", Consolas, Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #13161a; --surface: #1a1e23; --ink: #e9e7e2; --muted: #a3a9b0; --rule: #363c43; --rule-soft: #2a2f35;
    --ok-fg: #86d9a2; --ok-bg: #1b3326;
    --waived-fg: #92c6f0; --waived-bg: #1a2b3b;
    --stale-fg: #ebc56f; --stale-bg: #3a2f13;
    --inc-fg: #bcaef0; --inc-bg: #2a2546;
    --bad-fg: #ff9d95; --bad-bg: #3e1c1a;
    --limit: #e9e7e2; --track: #272c32;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.55 var(--sans); font-variant-numeric: tabular-nums;
}
::selection { background: var(--ink); color: var(--bg); }
main { max-width: 68rem; margin: 0 auto; padding: 2.5rem 1rem 3rem; }
h1, h2, h3 { font-family: var(--serif); font-weight: 600; line-height: 1.2; text-wrap: balance; margin: 0; }
h1 { font-size: clamp(1.9rem, 4vw, 2.6rem); letter-spacing: -0.01em; }
h2 { font-size: 1.45rem; margin-top: 3rem; padding-bottom: .5rem; border-bottom: 1px solid var(--rule); }
h3 { font-size: 1.1rem; }
p { margin: .5rem 0; max-width: 70ch; }
code, .mono { font-family: var(--mono); font-size: .86em; }
.muted { color: var(--muted); }
a { color: inherit; text-underline-offset: .2em; }
:focus-visible { outline: 3px solid var(--waived-fg); outline-offset: 2px; border-radius: 2px; }

header.top { display: grid; gap: .9rem; }
.meta { display: flex; flex-wrap: wrap; gap: .25rem 1.75rem; margin: 0; color: var(--muted); font-size: .9rem; }
.meta div { display: flex; gap: .4rem; }
.meta dt { margin: 0; }
.meta dd { margin: 0; color: var(--ink); }
.disclaimer {
  margin: 1.4rem 0 0; padding: .9rem 1.1rem; background: var(--surface);
  border: 1px solid var(--rule); border-radius: 4px; font-family: var(--serif); font-size: 1.05rem; max-width: none;
}

.verdict { margin: 2rem 0 0; font-family: var(--serif); font-size: 1.35rem; max-width: 60ch; text-wrap: pretty; }
.bar { display: flex; height: 14px; margin: 1rem 0 .75rem; border-radius: 2px; overflow: hidden; background: var(--track); }
.bar span { display: block; min-width: 4px; }
.bar .s-supported { background: var(--ok-fg); } .bar .s-waived { background: var(--waived-fg); }
.bar .s-stale { background: var(--stale-fg); } .bar .s-inconclusive { background: var(--inc-fg); }
.bar .s-violated { background: var(--bad-fg); }
.legend { display: flex; flex-wrap: wrap; gap: .5rem; list-style: none; padding: 0; margin: 0; }
.legend li { display: contents; }

.badge {
  display: inline-flex; align-items: center; gap: .4rem; padding: .15rem .6rem .15rem .45rem;
  border-radius: 999px; font-size: .8rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; white-space: nowrap;
}
.badge svg { width: 1.05em; height: 1.05em; flex: none; }
.badge .n { font-weight: 500; text-transform: none; letter-spacing: 0; opacity: .85; }
.b-supported { color: var(--ok-fg); background: var(--ok-bg); }
.b-waived { color: var(--waived-fg); background: var(--waived-bg); }
.b-stale { color: var(--stale-fg); background: var(--stale-bg); }
.b-inconclusive { color: var(--inc-fg); background: var(--inc-bg); }
.b-violated { color: var(--bad-fg); background: var(--bad-bg); }

table { width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: .93rem; }
caption { text-align: left; color: var(--muted); font-size: .85rem; padding-bottom: .4rem; }
th, td { text-align: left; vertical-align: top; padding: .6rem .75rem .6rem 0; border-bottom: 1px solid var(--rule-soft); }
thead th { font-size: .78rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); border-bottom: 1px solid var(--rule); }
td.num, th.num { text-align: right; padding-right: 1rem; }
.scroll { overflow-x: auto; }
.reasons { margin: 0; padding: 0; list-style: none; }
.reasons li + li { margin-top: .25rem; }
.reasons .code { font-family: var(--mono); font-size: .8rem; }

section.claim { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid var(--rule); break-inside: avoid; }
section.claim header { display: flex; flex-wrap: wrap; align-items: baseline; gap: .4rem 1rem; }
section.claim .req { margin: .35rem 0 0; color: var(--muted); }
.ev { display: grid; grid-template-columns: minmax(11rem, 17rem) minmax(14rem, 1fr) minmax(8rem, auto); gap: .25rem 1.25rem;
  align-items: center; margin-top: .9rem; }
.ev + .ev { padding-top: .6rem; border-top: 1px dotted var(--rule); }
.ev .who { font-size: .88rem; overflow-wrap: anywhere; }
.ev .who b { font-weight: 600; }
.ev .vals { font-size: .85rem; text-align: right; white-space: nowrap; }
svg.range { width: 100%; height: 34px; display: block; overflow: visible; }
svg.range .track { fill: var(--track); }
svg.range .over { fill: url(#hatch); }
svg.range .iv { fill: var(--ink); opacity: .78; }
svg.range .iv.pass { fill: var(--ok-fg); } svg.range .iv.fail { fill: var(--bad-fg); } svg.range .iv.inconclusive { fill: var(--inc-fg); }
svg.range .pt { fill: var(--surface); stroke: var(--ink); stroke-width: 1.5; }
svg.range .lim { stroke: var(--limit); stroke-width: 2; }
svg.range text { fill: var(--muted); font: 10.5px var(--sans); }
svg.range text.limt { fill: var(--ink); font-weight: 600; }
.hatch-line { stroke: var(--muted); stroke-width: 1; opacity: .55; }
.none { color: var(--muted); font-style: italic; margin-top: .75rem; }

dl.kv { display: grid; grid-template-columns: max-content 1fr; gap: .35rem 1.25rem; margin: 1rem 0 0; }
dl.kv dt { color: var(--muted); } dl.kv dd { margin: 0; overflow-wrap: anywhere; }
.hash { font-family: var(--mono); font-size: .8rem; overflow-wrap: anywhere; }
footer { margin-top: 3.5rem; padding-top: 1.25rem; border-top: 2px solid var(--ink); }
footer .disclaimer { margin-top: 1rem; }

@media (max-width: 40rem) {
  main { padding-top: 1.5rem; }
  .ev { grid-template-columns: 1fr; }
  .ev .vals { text-align: left; }
}
@media print {
  :root { --bg: #fff; --surface: #fff; --ink: #000; --muted: #333; --rule: #999; --rule-soft: #ccc; --track: #eee; }
  body { font-size: 11pt; }
  main { max-width: none; padding: 0; }
  .badge { border: 1px solid currentColor; }
  h2 { break-after: avoid; }
  tr, .ev { break-inside: avoid; }
  a { text-decoration: none; }
}
"""

# One sprite, referenced with <use>. Shapes differ per status so the word and the shape both carry meaning.
ICONS = """<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false">
<defs>
<pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line class="hatch-line" x1="0" y1="0" x2="0" y2="6"/></pattern>
<symbol id="i-supported" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.5" fill="currentColor"/><path d="M4.8 8.2l2.2 2.2 4.2-4.6" fill="none" stroke="var(--surface)" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-waived" viewBox="0 0 16 16"><circle cx="8" cy="8" r="5.8" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M5.3 8.1l1.9 1.9 3.5-3.9" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="i-stale" viewBox="0 0 16 16"><path d="M8 1.8L14.6 13.4H1.4Z" fill="currentColor" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M8 6v3.6M8 11.5v.1" stroke="var(--surface)" stroke-width="1.8" stroke-linecap="round"/></symbol>
<symbol id="i-inconclusive" viewBox="0 0 16 16"><path d="M8 1.2L14.8 8 8 14.8 1.2 8Z" fill="currentColor"/><path d="M6.3 6.3a1.8 1.8 0 113 1.2c-.7.6-1.3.9-1.3 1.7M8 11.2v.1" fill="none" stroke="var(--surface)" stroke-width="1.6" stroke-linecap="round"/></symbol>
<symbol id="i-violated" viewBox="0 0 16 16"><path d="M5.2 1.5h5.6l3.7 3.7v5.6l-3.7 3.7H5.2L1.5 10.8V5.2Z" fill="currentColor"/><path d="M5.6 5.6l4.8 4.8M10.4 5.6l-4.8 4.8" stroke="var(--surface)" stroke-width="1.8" stroke-linecap="round"/></symbol>
</defs>
</svg>"""
