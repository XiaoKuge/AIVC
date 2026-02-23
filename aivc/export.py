"""Export the knowledge graph to various formats."""

from __future__ import annotations

import csv
from pathlib import Path

import networkx as nx

from aivc.graph import COMPANY, FIRM, INVESTED_IN, PERSON, KnowledgeGraph


def to_graphml(kg: KnowledgeGraph, path: str | Path) -> None:
    """Export graph to GraphML format."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(kg.g, str(path))


def to_csv(kg: KnowledgeGraph, output_dir: str | Path) -> None:
    """Export graph to CSV files (nodes and edges)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Export nodes
    _export_nodes_csv(kg, output_dir / "firms.csv", FIRM)
    _export_nodes_csv(kg, output_dir / "companies.csv", COMPANY)
    _export_nodes_csv(kg, output_dir / "people.csv", PERSON)

    # Export edges
    _export_edges_csv(kg, output_dir / "investments.csv", INVESTED_IN)


def _export_nodes_csv(kg: KnowledgeGraph, path: Path, node_type: str) -> None:
    """Export nodes of a specific type to CSV."""
    nodes = kg.nodes_by_type(node_type)
    if not nodes:
        return

    # Collect all unique keys across nodes
    all_keys = set()
    for _, attrs in nodes:
        all_keys.update(attrs.keys())
    all_keys.discard("node_type")
    fieldnames = ["id"] + sorted(all_keys)

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for nid, attrs in nodes:
            row = {"id": nid, **attrs}
            writer.writerow(row)


def _export_edges_csv(kg: KnowledgeGraph, path: Path, edge_type: str) -> None:
    """Export edges of a specific type to CSV."""
    edges = kg.edges_by_type(edge_type)
    if not edges:
        return

    all_keys = set()
    for _, _, data in edges:
        all_keys.update(data.keys())
    all_keys.discard("edge_type")
    fieldnames = ["source", "target"] + sorted(all_keys)

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for src, dst, data in edges:
            row = {"source": src, "target": dst, **data}
            writer.writerow(row)
