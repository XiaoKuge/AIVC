#!/usr/bin/env python3
"""Rebuild the full knowledge graph from scratch.

Runs all pipeline steps in the correct order so no data is ever lost:
  1. Seed from XLSX (base firms, companies, people)
  2. Enrich companies (websites, sectors from company_metadata.json)
  3. Import curated deals (curated_deals.json)
  4. Enrich dates (investment_dates.json)
  5. Regenerate visualization (viz/generate.py → public/index.html)

Usage:
    python scripts/rebuild.py
    python scripts/rebuild.py --no-viz     # skip visualization
    python scripts/rebuild.py --dry-run    # show stats without saving
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aivc.graph import INVESTED_IN, PARTNER_AT, PERSONAL_INVESTMENT, KnowledgeGraph
from aivc.ingest import ingest_deals_json, ingest_xlsx

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GRAPH_PATH = DATA_DIR / "graph.json"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
DEALS_PATH = DATA_DIR / "raw" / "curated_deals.json"
META_PATH = DATA_DIR / "company_metadata.json"
DATES_PATH = DATA_DIR / "investment_dates.json"
PUBLIC_HTML = Path(__file__).resolve().parent.parent / "public" / "index.html"


def step_seed() -> KnowledgeGraph:
    """Step 1: Ingest XLSX seed data."""
    print("=" * 60)
    print("Step 1/5: Seeding from XLSX")
    print("=" * 60)
    kg = ingest_xlsx()
    stats = kg.stats()
    print(f"  {stats['total_nodes']} nodes, {stats['total_edges']} edges")
    return kg


def step_enrich_companies(kg: KnowledgeGraph) -> None:
    """Step 2: Enrich companies with metadata (websites, sectors)."""
    print("\n" + "=" * 60)
    print("Step 2/5: Enriching companies (company_metadata.json)")
    print("=" * 60)
    if not META_PATH.exists():
        print("  Skipped — company_metadata.json not found")
        return

    with open(META_PATH) as f:
        meta = json.load(f)

    to_remove = set(meta.pop("_remove", []))
    meta.pop("_note", None)

    removed = 0
    for nid in to_remove:
        if nid in kg.g:
            kg.g.remove_node(nid)
            removed += 1

    enriched = 0
    for nid, attrs in meta.items():
        if nid in kg.g:
            for k, v in attrs.items():
                if v not in (None, ""):
                    kg.g.nodes[nid][k] = v
            enriched += 1

    print(f"  Removed {removed} junk nodes, enriched {enriched} companies")


def step_import_deals(kg: KnowledgeGraph) -> None:
    """Step 3: Import curated deals."""
    print("\n" + "=" * 60)
    print("Step 3/5: Importing curated deals")
    print("=" * 60)
    if not DEALS_PATH.exists():
        print("  Skipped — curated_deals.json not found")
        return

    count = ingest_deals_json(kg, DEALS_PATH)
    print(f"  Imported {count} deals")


def step_enrich_dates(kg: KnowledgeGraph) -> None:
    """Step 4: Enrich investment edges with dates."""
    print("\n" + "=" * 60)
    print("Step 4/5: Enriching investment dates")
    print("=" * 60)
    if not DATES_PATH.exists():
        print("  Skipped — investment_dates.json not found")
        return

    with open(DATES_PATH) as f:
        dates_map = json.load(f)
    dates_map.pop("_note", None)

    enriched = 0
    total = 0
    for edge_type in (INVESTED_IN, PARTNER_AT, PERSONAL_INVESTMENT):
        for src, dst, data in kg.edges_by_type(edge_type):
            total += 1
            key = f"{src}::{dst}"
            if key in dates_map and not data.get("date"):
                data["date"] = dates_map[key]
                enriched += 1

    missing = total - enriched
    print(f"  Enriched {enriched}/{total} edges with dates")
    if missing:
        print(f"  Warning: {missing} investments still missing dates")


def step_generate_viz() -> None:
    """Step 5: Regenerate visualization and copy to public/."""
    print("\n" + "=" * 60)
    print("Step 5/5: Generating visualization")
    print("=" * 60)
    try:
        from viz.generate import generate_html

        output = generate_html()
        shutil.copy2(output, PUBLIC_HTML)
        print(f"  Generated: {output}")
        print(f"  Copied to: {PUBLIC_HTML}")
    except Exception as e:
        print(f"  Error: {e}")
        print("  Run manually: python viz/generate.py")


def main():
    parser = argparse.ArgumentParser(description="Rebuild full knowledge graph")
    parser.add_argument("--no-viz", action="store_true",
                        help="Skip visualization regeneration")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show stats without saving")
    args = parser.parse_args()

    # Snapshot existing graph before rebuild
    if not args.dry_run and GRAPH_PATH.exists():
        SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot = SNAPSHOTS_DIR / f"graph_{ts}.json"
        shutil.copy2(GRAPH_PATH, snapshot)
        print(f"Snapshot saved: {snapshot}\n")

    # Run all pipeline steps
    kg = step_seed()
    step_enrich_companies(kg)
    step_import_deals(kg)
    step_enrich_dates(kg)

    # Final stats
    stats = kg.stats()
    print("\n" + "=" * 60)
    print("Final graph")
    print("=" * 60)
    print(f"  Nodes: {stats['total_nodes']} "
          f"(firms: {stats['firms']}, companies: {stats['companies']}, people: {stats['people']})")
    print(f"  Edges: {stats['total_edges']} "
          f"(investments: {stats['investments']}, partnerships: {stats['partnerships']})")

    if args.dry_run:
        print("\n(Dry run — graph not saved)")
        return

    kg.save(GRAPH_PATH)
    print(f"\nGraph saved to {GRAPH_PATH}")

    if not args.no_viz:
        step_generate_viz()

    print("\nDone.")


if __name__ == "__main__":
    main()
