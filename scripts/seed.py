#!/usr/bin/env python3
"""One-time seed: parse XLSX and generate initial graph.json."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aivc.ingest import ingest_xlsx

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GRAPH_PATH = DATA_DIR / "graph.json"


def main():
    print("Ingesting XLSX...")
    kg = ingest_xlsx()

    stats = kg.stats()
    print(f"\nGraph statistics:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print(f"\nSaving to {GRAPH_PATH}...")
    kg.save(GRAPH_PATH)
    print("Done.")


if __name__ == "__main__":
    main()
