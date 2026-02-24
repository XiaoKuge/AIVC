#!/usr/bin/env python3
"""Validate the knowledge graph for data quality.

Checks:
- Every invested_in edge has a source_url or source field
- No orphan nodes (zero edges)
- No duplicate entity names with different IDs
- Coverage stats (% with sector, dates, websites, etc.)

Usage:
    python scripts/validate_graph.py
    python scripts/validate_graph.py --fix  # auto-fix simple issues
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aivc.graph import INVESTED_IN, KnowledgeGraph

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GRAPH_PATH = DATA_DIR / "graph.json"


def validate_sources(kg: KnowledgeGraph) -> list[str]:
    """Check that investment edges have source attribution."""
    issues = []
    for src, dst, data in kg.edges_by_type(INVESTED_IN):
        source = data.get("source", "")
        if not source:
            src_name = kg.g.nodes[src].get("name", src)
            dst_name = kg.g.nodes[dst].get("name", dst)
            issues.append(f"Missing source: {src_name} -> {dst_name}")
    return issues


def find_orphans(kg: KnowledgeGraph) -> list[tuple[str, str]]:
    """Find nodes with zero edges."""
    orphans = []
    for nid, attrs in kg.g.nodes(data=True):
        if kg.g.degree(nid) == 0:
            node_type = attrs.get("node_type", "unknown")
            name = attrs.get("name", nid)
            orphans.append((nid, f"{name} ({node_type})"))
    return orphans


def find_duplicate_names(kg: KnowledgeGraph) -> list[tuple[str, list[str]]]:
    """Find entity names that map to multiple node IDs."""
    name_to_ids = defaultdict(list)
    for nid, attrs in kg.g.nodes(data=True):
        name = attrs.get("name", "").lower().strip()
        if name:
            name_to_ids[name].append(nid)

    duplicates = []
    for name, ids in name_to_ids.items():
        if len(ids) > 1:
            duplicates.append((name, ids))
    return duplicates


def coverage_stats(kg: KnowledgeGraph) -> dict:
    """Compute coverage statistics."""
    stats = {}

    # Company coverage
    companies = kg.companies()
    total_companies = len(companies)
    if total_companies > 0:
        with_sector = sum(1 for _, a in companies if a.get("sector"))
        with_website = sum(1 for _, a in companies if a.get("website"))
        with_year = sum(1 for _, a in companies if a.get("founded_year"))
        stats["companies"] = {
            "total": total_companies,
            "with_sector": with_sector,
            "pct_sector": round(100 * with_sector / total_companies, 1),
            "with_website": with_website,
            "pct_website": round(100 * with_website / total_companies, 1),
            "with_founded_year": with_year,
            "pct_founded_year": round(100 * with_year / total_companies, 1),
        }

    # Firm coverage
    firms = kg.firms()
    total_firms = len(firms)
    if total_firms > 0:
        with_region = sum(1 for _, a in firms if a.get("hq_region"))
        with_website = sum(1 for _, a in firms if a.get("website"))
        with_aum = sum(1 for _, a in firms if a.get("aum"))
        stats["firms"] = {
            "total": total_firms,
            "with_hq_region": with_region,
            "pct_hq_region": round(100 * with_region / total_firms, 1),
            "with_website": with_website,
            "pct_website": round(100 * with_website / total_firms, 1),
            "with_aum": with_aum,
            "pct_aum": round(100 * with_aum / total_firms, 1),
        }

    # Investment edge coverage
    investments = kg.edges_by_type(INVESTED_IN)
    total_inv = len(investments)
    if total_inv > 0:
        with_date = sum(1 for _, _, d in investments if d.get("date"))
        with_amount = sum(1 for _, _, d in investments if d.get("amount"))
        with_round = sum(1 for _, _, d in investments if d.get("round"))
        with_source = sum(1 for _, _, d in investments if d.get("source"))
        stats["investments"] = {
            "total": total_inv,
            "with_date": with_date,
            "pct_date": round(100 * with_date / total_inv, 1),
            "with_amount": with_amount,
            "pct_amount": round(100 * with_amount / total_inv, 1),
            "with_round": with_round,
            "pct_round": round(100 * with_round / total_inv, 1),
            "with_source": with_source,
            "pct_source": round(100 * with_source / total_inv, 1),
        }

    # Source distribution
    source_counts = Counter()
    for _, _, d in kg.g.edges(data=True):
        source = d.get("source", "unknown")
        # Normalize source prefix
        prefix = source.split(":")[0] if ":" in source else source
        source_counts[prefix] += 1
    stats["source_distribution"] = dict(source_counts.most_common())

    return stats


def remove_orphans(kg: KnowledgeGraph, orphans: list[tuple[str, str]]) -> int:
    """Remove orphan nodes from the graph."""
    removed = 0
    for nid, _ in orphans:
        kg.g.remove_node(nid)
        removed += 1
    return removed


def main():
    parser = argparse.ArgumentParser(description="Validate knowledge graph data quality")
    parser.add_argument("--fix", action="store_true",
                        help="Auto-fix simple issues (remove orphans)")
    args = parser.parse_args()

    if not GRAPH_PATH.exists():
        print(f"Graph not found: {GRAPH_PATH}")
        sys.exit(1)

    kg = KnowledgeGraph.load(GRAPH_PATH)
    basic = kg.stats()

    print("=" * 60)
    print("AIVC Knowledge Graph Validation Report")
    print("=" * 60)

    print(f"\nGraph summary:")
    print(f"  Nodes: {basic['total_nodes']} (Firms: {basic['firms']}, "
          f"Companies: {basic['companies']}, People: {basic['people']})")
    print(f"  Edges: {basic['total_edges']} (Investments: {basic['investments']}, "
          f"Partnerships: {basic['partnerships']}, Personal: {basic['personal_investments']})")

    # Check sources
    print(f"\n--- Source Attribution ---")
    source_issues = validate_sources(kg)
    if source_issues:
        print(f"  WARNING: {len(source_issues)} investment edges missing source")
        for issue in source_issues[:10]:
            print(f"    {issue}")
        if len(source_issues) > 10:
            print(f"    ... and {len(source_issues) - 10} more")
    else:
        print("  OK: All investment edges have source attribution")

    # Check orphans
    print(f"\n--- Orphan Nodes ---")
    orphans = find_orphans(kg)
    if orphans:
        print(f"  WARNING: {len(orphans)} orphan nodes (zero edges)")
        for _, desc in orphans[:10]:
            print(f"    {desc}")
        if len(orphans) > 10:
            print(f"    ... and {len(orphans) - 10} more")

        if args.fix:
            removed = remove_orphans(kg, orphans)
            print(f"  FIXED: Removed {removed} orphan nodes")
    else:
        print("  OK: No orphan nodes")

    # Check duplicates
    print(f"\n--- Duplicate Names ---")
    duplicates = find_duplicate_names(kg)
    if duplicates:
        print(f"  WARNING: {len(duplicates)} names with multiple IDs")
        for name, ids in duplicates[:10]:
            print(f"    '{name}' -> {ids}")
        if len(duplicates) > 10:
            print(f"    ... and {len(duplicates) - 10} more")
    else:
        print("  OK: No duplicate entity names")

    # Coverage stats
    print(f"\n--- Coverage Statistics ---")
    stats = coverage_stats(kg)

    if "companies" in stats:
        c = stats["companies"]
        print(f"\n  Companies ({c['total']}):")
        print(f"    Sector:       {c['with_sector']:>4} / {c['total']} ({c['pct_sector']}%)")
        print(f"    Website:      {c['with_website']:>4} / {c['total']} ({c['pct_website']}%)")
        print(f"    Founded year: {c['with_founded_year']:>4} / {c['total']} ({c['pct_founded_year']}%)")

    if "firms" in stats:
        f = stats["firms"]
        print(f"\n  Firms ({f['total']}):")
        print(f"    HQ region:    {f['with_hq_region']:>4} / {f['total']} ({f['pct_hq_region']}%)")
        print(f"    Website:      {f['with_website']:>4} / {f['total']} ({f['pct_website']}%)")
        print(f"    AUM:          {f['with_aum']:>4} / {f['total']} ({f['pct_aum']}%)")

    if "investments" in stats:
        i = stats["investments"]
        print(f"\n  Investments ({i['total']}):")
        print(f"    Date:         {i['with_date']:>4} / {i['total']} ({i['pct_date']}%)")
        print(f"    Amount:       {i['with_amount']:>4} / {i['total']} ({i['pct_amount']}%)")
        print(f"    Round:        {i['with_round']:>4} / {i['total']} ({i['pct_round']}%)")
        print(f"    Source:       {i['with_source']:>4} / {i['total']} ({i['pct_source']}%)")

    if "source_distribution" in stats:
        print(f"\n  Source distribution:")
        for source, count in stats["source_distribution"].items():
            print(f"    {source}: {count}")

    # Save if fixes were applied
    if args.fix and orphans:
        kg.save(GRAPH_PATH)
        print(f"\nGraph saved with fixes to {GRAPH_PATH}")

    # Overall verdict
    print(f"\n{'='*60}")
    total_issues = len(source_issues) + len(orphans) + len(duplicates)
    if total_issues == 0:
        print("PASS: No issues found")
    else:
        print(f"ISSUES: {total_issues} total ({len(source_issues)} missing sources, "
              f"{len(orphans)} orphans, {len(duplicates)} duplicates)")


if __name__ == "__main__":
    main()
