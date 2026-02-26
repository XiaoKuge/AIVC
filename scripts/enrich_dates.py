#!/usr/bin/env python3
"""Enrich investment edges with approximate dates from public data."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aivc.graph import INVESTED_IN, PARTNER_AT, PERSONAL_INVESTMENT, KnowledgeGraph

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GRAPH_PATH = DATA_DIR / "graph.json"
DATES_PATH = DATA_DIR / "investment_dates.json"


def main():
    with open(DATES_PATH) as f:
        dates_map = json.load(f)
    # Remove the _note key
    dates_map.pop("_note", None)

    kg = KnowledgeGraph.load(GRAPH_PATH)

    enriched = 0
    total = 0
    for edge_type in (INVESTED_IN, PARTNER_AT, PERSONAL_INVESTMENT):
        for src, dst, data in kg.edges_by_type(edge_type):
            total += 1
            key = f"{src}::{dst}"
            if key in dates_map and not data.get("date"):
                data["date"] = dates_map[key]
                enriched += 1

    print(f"Enriched {enriched}/{total} edges with dates")
    kg.save(GRAPH_PATH)
    print(f"Saved to {GRAPH_PATH}")


if __name__ == "__main__":
    main()
