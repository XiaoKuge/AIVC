# Development Journey

A chronological record of how the AI VC Knowledge Graph was built, the decisions made, and lessons learned along the way.

---

## Day 1 — Feb 22, 2026: Foundation

### Bootstrapping the knowledge graph

Built the entire core stack in a single session:

- **Data model**: Pydantic models (`VCFirm`, `Company`, `Person`, `Deal`) with a NetworkX `MultiDiGraph` wrapper supporting idempotent merge — so re-running scrapers never creates duplicates.
- **Ingestion**: XLSX parser that reads a curated spreadsheet of 92 VC firms, 141+ companies, and 23 notable investors. Edges capture `invested_in`, `partner_at`, and `personal_investment` relationships.
- **Visualization**: Pyvis-generated interactive HTML with a dual-thumb timeline slider, click-to-focus subgraph view, HTML tooltips with metadata, and double-click to open external URLs.
- **Query layer**: CLI for portfolio lookups, co-investor analysis, and entity search.
- **Tests**: 28 tests covering graph operations, ingestion, and queries.

**Key decision**: Using NetworkX `MultiDiGraph` (not `DiGraph`) to support multiple investment rounds between the same firm→company pair (e.g., Series A then Series B). Each round gets a stable edge key like `invested_in:Series A:2025-03`.

### Bloomberg terminal aesthetic

Applied a dark theme inspired by Bloomberg terminals — `#0A0A0A` background, monospace fonts (`SF Mono` / `Fira Code`), amber/green/cyan color scheme. Added a fixed header with live node/edge counter.

**Result**: 307 nodes, 336 edges, fully interactive graph.

---

## Day 2 — Feb 23, 2026: Data expansion & visual polish

### Curated deals pipeline

Built infrastructure for importing verified deals from news articles:

- `ingest_deals_json()` for bulk importing deal records with amount, round, date, and source URL.
- `scripts/curate_deals.py` for fetching articles and extracting deals via LLM.
- Expanded the alias system from 11 to ~85 entries (covering Chinese AI companies, 2025-2026 entities).
- **40 curated deals** added: OpenAI $40B, Anthropic $30B, xAI, Cursor, and more.

### Logos and avatars

Added visual identity to nodes in focus mode:
- Companies/VCs get favicons via Google's favicon API (`google.com/s2/favicons?domain=...&sz=128`)
- People get initial-based avatars via `ui-avatars.com`
- Both appear in hover tooltips and the focus subgraph view as `circularImage` shapes.

### Mid-market deal coverage

Added 52 more deals beyond mega-rounds — robotics, AI healthcare, AI chips, AI security, seed/Series A in the $10M–$100M range. Graph grew to **418 nodes, 422 edges**.

### Breathing animation for recent nodes

Nodes with investments in the last 7 days pulse with a red glow ring, drawn via vis.js `afterDrawing` canvas callback at ~20fps. This was a fun one — the trick is to only draw overlay rings in the callback, never calling `nodes.update()` from inside the draw loop (that causes infinite recursion).

### Fit View button + Vercel deployment

- Added "Fit View" button to recenter after zooming.
- Fixed deployment: `viz/output/*.html` was gitignored, so Vercel never got the latest visualization. Solution: copy generated HTML to `public/index.html`.

---

## Day 3 — Feb 25, 2026: Pipeline hardening & share features

### Removing the LLM API dependency

The original pipeline required an `ANTHROPIC_API_KEY` to extract deals from articles. Refactored to separate fetching (automated, runs in GitHub Action) from extraction (done via Claude Code locally). This means the CI pipeline doesn't need API keys.

Added 24 more deals (Moonshot AI, MatX, LimX, etc.) — graph reached **447 nodes, 446 edges**.

### Share URL + Export PNG

Two complementary features for sharing the visualization state:

- **Share URL**: Encodes focused node + timeline filters in URL hash (`#focus=anthropic&ymin=2024`). Recipients see the same semantic state (though physics layout differs). Includes clipboard copy with "Copied!" feedback and `execCommand` fallback.
- **Export PNG**: Downloads the vis.js canvas as an image for slides/email/chat. Uses `canvas.toDataURL('image/png')` with try/catch for CORS-tainted canvas.
- **URL sync**: Hash updates live as the user clicks nodes and adjusts sliders.

### Hover breathing glow

Extended the breathing animation to work on hover — when you mouse over any node, it and its connected neighbors/edges glow with the node's own color. The key challenge was the vis.js built-in tooltip creating a DOM overlay that intercepted mouse events, causing rapid hover/blur cycling. Fixed by removing `title` from vis.js nodes entirely and routing tooltip HTML through a separate JS object to the custom tooltip handler.

### Timeline centering + double tooltip fix

- Centered the bottom timeline bar by removing the `max-width` constraint and the "Timeline" label.
- Fixed duplicate tooltips: vis.js built-in tooltip was showing alongside the custom dark tooltip. Root cause was the `title` property on nodes/edges — removed it, keeping only the custom tooltip system.

### Event recording + dossier carousel (走马灯)

The biggest feature of the day. Three-layer implementation:

**Data layer** (`aivc/models.py`, `aivc/graph.py`):
- New `Event` model: `type`, `date`, `description`, `source_url`.
- `_merge_node()` records `"created"` events on first add, `"updated"` events with changed field names on subsequent merges.
- `_merge_edge()` records `"invested"` / `"partnered"` / `"personal_inv"` events with human-readable descriptions (`"A16Z → OpenAI | Series A | $500M"`).
- `_extract_source_url()` pulls URLs from source strings like `"curated:https://..."`.

**Visualization** (`viz/generate.py`):
- Events collected from all nodes/edges and serialized to JSON.
- New **Event Dossier modal** — centered dark overlay with spy-movie aesthetic:
  - "INTEL" header with entity name and event count.
  - Color-coded type badges (green=created, cyan=updated, amber=invested).
  - Carousel navigation: `← prev | 2/3 | next →`.
  - Keyboard: Left/Right arrows to flip, Escape to close. Click outside to dismiss.
- Node click → focus mode + dossier opens.
- Edge click → dossier opens for that edge's events.

---

## Architecture Notes

### File structure

```
aivc/
  models.py      — Pydantic models (VCFirm, Company, Person, Deal, Event)
  graph.py       — NetworkX MultiDiGraph wrapper with idempotent merge + event recording
  ingest.py      — XLSX parser + curated deals JSON importer
  query.py       — Portfolio, co-investor, and search queries
  extract.py     — Deal extraction from article text
  state.py       — Pipeline state tracking (processed URLs)
viz/
  generate.py    — Pyvis HTML generation (~1500 lines of Python + inline JS/CSS)
data/
  graph.json     — Serialized knowledge graph (node-link format)
  aliases.json   — Entity name normalization
  raw/           — Source data (XLSX, curated deals JSON)
public/
  index.html     — Generated visualization served by Vercel
```

### Design principles

1. **Idempotent everything** — Re-running any ingestion pipeline produces the same result. Merge logic only overwrites fields with non-empty values.
2. **Stable edge keys** — `{edge_type}:{round}:{date}` ensures multiple investment rounds coexist without duplication.
3. **Single-file visualization** — The entire interactive UI is one self-contained HTML file with inline CSS/JS. No build step, no framework, just Pyvis + vis.js + hand-written scripts.
4. **Events as provenance** — Every data change is recorded with timestamp and source URL, creating an audit trail viewable in the dossier carousel.
