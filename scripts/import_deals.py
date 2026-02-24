#!/usr/bin/env python3
"""Import curated deals into the knowledge graph.

Loads the existing graph, ingests deals from curated_deals.json,
saves the updated graph, and regenerates the visualization.

Usage:
    python scripts/import_deals.py
    python scripts/import_deals.py --deals path/to/deals.json
    python scripts/import_deals.py --dry-run
    python scripts/import_deals.py --no-viz  # skip visualization regeneration
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aivc.graph import KnowledgeGraph
from aivc.ingest import ingest_deals_json

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GRAPH_PATH = DATA_DIR / "graph.json"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
DEFAULT_DEALS = DATA_DIR / "raw" / "curated_deals.json"


def main():
    parser = argparse.ArgumentParser(description="Import curated deals into knowledge graph")
    parser.add_argument("--deals", "-d", default=str(DEFAULT_DEALS),
                        help="Path to curated deals JSON file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Load and count but don't save")
    parser.add_argument("--no-viz", action="store_true",
                        help="Skip visualization regeneration")
    args = parser.parse_args()

    deals_path = Path(args.deals)
    if not deals_path.exists():
        print(f"Deals file not found: {deals_path}")
        sys.exit(1)

    # Load existing graph
    if GRAPH_PATH.exists():
        print(f"Loading graph from {GRAPH_PATH}")
        kg = KnowledgeGraph.load(GRAPH_PATH)
    else:
        print("No existing graph found, starting fresh")
        kg = KnowledgeGraph()

    before = kg.stats()
    print(f"Before: {before['total_nodes']} nodes, {before['total_edges']} edges")

    # Create snapshot before modifying
    if not args.dry_run and GRAPH_PATH.exists():
        SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_path = SNAPSHOTS_DIR / f"graph_{ts}.json"
        shutil.copy2(GRAPH_PATH, snapshot_path)
        print(f"Snapshot saved: {snapshot_path}")

    # Ingest deals
    count = ingest_deals_json(kg, deals_path)
    after = kg.stats()

    new_nodes = after["total_nodes"] - before["total_nodes"]
    new_edges = after["total_edges"] - before["total_edges"]

    print(f"\nIngested {count} deals")
    print(f"After:  {after['total_nodes']} nodes (+{new_nodes}), "
          f"{after['total_edges']} edges (+{new_edges})")
    print(f"  Firms: {after['firms']}, Companies: {after['companies']}, "
          f"People: {after['people']}")
    print(f"  Investments: {after['investments']}, Partnerships: {after['partnerships']}")

    if args.dry_run:
        print("\n(Dry run — graph not saved)")
        return

    # Save updated graph
    kg.save(GRAPH_PATH)
    print(f"\nGraph saved to {GRAPH_PATH}")

    # Regenerate visualization
    if not args.no_viz:
        print("Regenerating visualization...")
        try:
            from viz.generate import generate_html
            output = generate_html()
            print(f"Visualization saved to {output}")
        except Exception as e:
            print(f"Warning: Could not regenerate viz: {e}")
            print("Run manually: python viz/generate.py")
    else:
        print("Skipping visualization (--no-viz)")


if __name__ == "__main__":
    main()
