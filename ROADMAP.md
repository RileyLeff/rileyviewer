# Roadmap

Ideas and future directions. Nothing here is promised or scheduled.

## v0.1 (current)

- Standalone Rust server (`brew install`, `cargo install`, or GitHub release binaries)
- Pure Python HTTP client (`uv add rileyviewer`) — connects to running server, no binary bundled
- matplotlib, seaborn, pandas plots, Plotly, Altair, animations, HTML
- Browser UI with theme toggle, thumbnails, settings
- CLI pipe (`rileyviewer send`) — pipe files or stdin directly, auto-detects PNG/SVG/Plotly/Vega/HTML
- Keyboard shortcuts — arrow keys, Home/End, copy, reconnect, Escape

## Data tables

Render tabular data in the browser. Expands rileyviewer from "plot viewer" to "data viewer."

Wire format is per-format, not per-library — like how we support PNG/SVG/Plotly JSON rather than matplotlib/seaborn/ggplot2:

- **Arrow IPC** — binary columnar format. Compact, typed, fast. Every major DataFrame library speaks Arrow natively (pandas, polars, R arrow, Julia Arrow.jl). The `apache-arrow` JS library reads it in the browser.
- **CSV** — universal text fallback. Lossy on types but simple.

Client adapters are thin serializers:
- **Python** — `v.show(df)` detects pandas/polars → Arrow IPC bytes → POST
- **CLI** — `rileyviewer send data.csv`, `rileyviewer send data.parquet`
- **Browser** — virtual-scrolled table with column sorting, type-aware formatting, pagination

For large datasets (millions of rows), Arrow IPC + virtual scrolling handles the browser side. Server-side pagination (rows on demand) is the next step if needed.

## Export

Download the current plot with control over format, size, and resolution.

- **Format picker** — PNG, SVG, PDF. For Plotly/Vega, also offer the underlying JSON. For tables, CSV/Parquet.
- **Resize** — set custom width/height in pixels before export, with a live preview.
- **DPI control** — for raster formats, choose resolution (72 for screen, 300 for print, 600 for publication).
- **Batch export** — select multiple thumbnails (or a whole collection), export as a zip or multi-page PDF.
- **Copy to clipboard** — one-click copy as image, useful for pasting into Slack/docs. (Basic version already implemented via `c` shortcut.)

## File watcher

```bash
rileyviewer watch ./figures/
```

Auto-ingest new or modified image/SVG/HTML files from a directory. Zero integration effort — just point it at wherever your scripts dump output.

## Metadata, tags & collections

One unified system for organizing plots. Each layer builds on the one below it:

1. **Metadata** — every plot gets a title, freeform notes, and tags. Can be sent from Python (`v.show(fig, title="After fix", tags=["exp2", "final"])`) or added/edited in the browser.
2. **Tags** — lightweight labels like `"baseline"`, `"experiment-2"`, `"final"`. Applied from Python or via the browser UI.
3. **Collections** — saved tag filters or manual selections. Think playlists, not folders. Select a handful of plots from a session of 50 and group them.
4. **Filter bar** — thumbnail strip shows filter chips: `All (50) | baseline (8) | experiment-2 (12)`. Click to filter.
5. **Thumbnail UX** — hover shows title + timestamp + first line of notes. Right-click for: rename, add note, tag, copy to clipboard, delete.
6. **Search** — with enough plots, free-text search across titles, notes, and tags.

## Presentation mode

Fullscreen slideshow through your plots. Arrow keys to navigate, escape to exit.

- Presents the current filter/collection, not necessarily all plots.
- Pairs with collections: make a "results" collection, enter presentation mode, walk through it in a lab meeting.
- Optional auto-advance timer for unattended displays.

## Session snapshots

Save the entire session (all plots + metadata + annotations) as a single `.rvw` file. Send it to a colleague, they open it in their viewer, see everything. Like saving a Figma file — just a zip of JSON + embedded assets under the hood.

- `rileyviewer snapshot save session.rvw`
- `rileyviewer snapshot open session.rvw`
- Could also auto-snapshot periodically for crash recovery.

## Plot source tracking

Automatically capture and display the code that generated each plot. Click "source" on any plot to see it.

Client-side responsibility — each client library captures source info using language-native introspection and sends it as metadata alongside the plot:

- **Python** — `inspect.stack()` grabs file, line, surrounding code. Easiest.
- **R** — `sys.call()` + `sys.frame()` for call expression and source location.
- **JS/TS** — `new Error().stack` for file/line from V8 stack trace.
- **Julia** — `@__FILE__`, `@__LINE__`, `stacktrace()`. JIT'd so source usually available.

Compiled languages (Rust, Go) can skip this — not worth the complexity for file/line without source text.

The protocol is just a metadata field: `{"source": {"file": "experiment.py", "line": 42, "code": "..."}}`. Opt-in — clients that don't send it just don't have a source tab.

## Notifications

Desktop notification (or Slack webhook) when a new plot arrives. Kick off a long-running job, go do something else, get pinged when results land.

## Comparison grid

Select 2-4 thumbnails and tile them side by side. Essential for parameter sweeps, before/after, A/B comparisons.

## Annotation & markup

Doodle on figures, add notes, circle the interesting parts.

- **Excalidraw integration** — embed Excalidraw as an overlay layer on any plot. Draw arrows, circles, text annotations directly on figures. Excalidraw is MIT-licensed and has a React component, but there's also `@excalidraw/excalidraw` which could work in a Svelte wrapper.
- **Lighter alternative** — a simple canvas overlay with pen/arrow/text tools if Excalidraw is too heavy.
- **Persistence** — annotations saved alongside plots so they survive refresh. Could store as Excalidraw JSON in the plot metadata.
- **Multiplayer synergy** — if sessions are shared, annotations become collaborative. "Hey look at this cluster" *draws circle*.

## Multiplayer / shared sessions

Make rileyviewer collaborative — start a session, share a link, and labmates see plots in real-time.

- **Hosted relay** — a public server that proxies WebSocket connections so you don't need to expose localhost. Share a session URL like `rileyviewer.dev/s/abc123`.
- **Cursor-style presence** — see who's connected, maybe colored borders on plots showing who sent them.
- **Auth** — invite-only sessions, token-based access. The token system already exists locally; extending it to shared sessions is natural.
- **Use case** — pair programming on data analysis, lab meetings where everyone pushes figures to a shared board, code review where you reproduce someone's plots live.

Requires: a hosted component (relay server or tunneling), session management, identity.

## Polyglot clients

The server is language-agnostic — it accepts plots via HTTP POST as PNG, SVG, Plotly JSON, Vega/Vega-Lite JSON, or HTML. Any language with an HTTP client can send plots. Thin client libraries could be written for:

- **R** — wrap `ggsave()` → SVG → POST. Would let you interleave ggplot2 and seaborn in the same viewer.
- **JavaScript/TypeScript** — `fetch()` wrapper. Useful for Node scripts doing data processing.
- **Rust** — `ureq` or `reqwest` POST. Niche but fun for visualizing simulations.
- **Julia** — similar story, HTTP POST with Plots.jl/Makie.jl output.

The server is already installable standalone via Homebrew, Cargo, or GitHub releases.

## Other ideas

- **Clear/reset** — button or API call to clear the plot history
- **Reorder/delete** — drag to reorder or swipe to remove individual plots
- **Notebook integration** — `_repr_html_()` that embeds an iframe pointing at the viewer
- **WebSocket client mode** — subscribe to new plots programmatically (for testing, CI screenshots, etc.)
