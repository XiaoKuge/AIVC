#!/usr/bin/env python3
"""Enrich company nodes with sector, website, and founding year metadata."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aivc.graph import KnowledgeGraph

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GRAPH_PATH = DATA_DIR / "graph.json"
META_PATH = DATA_DIR / "company_metadata.json"


def main():
    with open(META_PATH) as f:
        meta = json.load(f)

    # Extract removal list
    to_remove = set(meta.pop("_remove", []))
    meta.pop("_note", None)

    kg = KnowledgeGraph.load(GRAPH_PATH)

    # Remove junk nodes (and their edges)
    removed = 0
    for nid in to_remove:
        if nid in kg.g:
            kg.g.remove_node(nid)
            removed += 1

    # Enrich company nodes
    enriched = 0
    for nid, attrs in meta.items():
        if nid in kg.g:
            for k, v in attrs.items():
                if v not in (None, ""):
                    kg.g.nodes[nid][k] = v
            enriched += 1

    print(f"Removed {removed} junk nodes")
    print(f"Enriched {enriched} companies with metadata")
    print(f"Graph: {kg.g.number_of_nodes()} nodes, {kg.g.number_of_edges()} edges")

    kg.save(GRAPH_PATH)
    print(f"Saved to {GRAPH_PATH}")


if __name__ == "__main__":
    main()
