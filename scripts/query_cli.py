#!/usr/bin/env python3
"""CLI for ad-hoc queries against the AI VC Knowledge Graph."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aivc.graph import KnowledgeGraph
from aivc.query import co_investors, firm_details, investors, portfolio, search

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GRAPH_PATH = DATA_DIR / "graph.json"


def cmd_portfolio(kg: KnowledgeGraph, args: argparse.Namespace) -> None:
    """Show portfolio companies for a firm."""
    firm = " ".join(args.name)
    results = portfolio(kg, firm)
    if not results:
        print(f"No portfolio found for '{firm}'. Try 'search' command.")
        return
    print(f"\nPortfolio of '{firm}' ({len(results)} companies):")
    for r in results:
        print(f"  - {r['name']}")


def cmd_investors(kg: KnowledgeGraph, args: argparse.Namespace) -> None:
    """Show investors in a company."""
    company = " ".join(args.name)
    results = investors(kg, company)
    if not results:
        print(f"No investors found for '{company}'. Try 'search' command.")
        return
    print(f"\nInvestors in '{company}' ({len(results)}):")
    for r in results:
        print(f"  - {r['name']} ({r.get('type', '')})")


def cmd_co_investors(kg: KnowledgeGraph, args: argparse.Namespace) -> None:
    """Show co-investors with a firm."""
    firm = " ".join(args.name)
    results = co_investors(kg, firm)
    if not results:
        print(f"No co-investors found for '{firm}'. Try 'search' command.")
        return
    print(f"\nCo-investors with '{firm}' ({len(results)} firms):")
    for r in results[:20]:  # Top 20
        shared = ", ".join(r["shared_companies"][:5])
        more = f" +{len(r['shared_companies']) - 5} more" if len(r["shared_companies"]) > 5 else ""
        print(f"  - {r['name']} ({r['count']} shared): {shared}{more}")


def cmd_details(kg: KnowledgeGraph, args: argparse.Namespace) -> None:
    """Show full details for a firm."""
    firm = " ".join(args.name)
    result = firm_details(kg, firm)
    if not result:
        print(f"Firm '{firm}' not found. Try 'search' command.")
        return
    print(f"\n{result.get('name', firm)}")
    print(f"  Type: {result.get('type', 'N/A')}")
    print(f"  HQ: {result.get('hq_city', 'N/A')} ({result.get('hq_region', 'N/A')})")
    print(f"  Stage: {result.get('stage_focus', 'N/A')}")
    print(f"  Check Size: {result.get('check_size', 'N/A')}")
    print(f"  AI Focus: {result.get('ai_focus', 'N/A')}")
    print(f"  AUM: {result.get('aum', 'N/A')}")
    if result.get("partners"):
        print(f"  Partners ({len(result['partners'])}):")
        for p in result["partners"]:
            print(f"    - {p['name']} ({p.get('title', '')})")
    if result.get("portfolio"):
        print(f"  Portfolio ({len(result['portfolio'])}):")
        for c in result["portfolio"]:
            print(f"    - {c['name']}")


def cmd_search(kg: KnowledgeGraph, args: argparse.Namespace) -> None:
    """Search for entities by name."""
    term = " ".join(args.term)
    results = search(kg, term)
    if not results:
        print(f"No results for '{term}'.")
        return
    print(f"\nSearch results for '{term}' ({len(results)}):")
    for r in results:
        print(f"  [{r['type']}] {r['name']} (id: {r['id']})")


def cmd_stats(kg: KnowledgeGraph, _args: argparse.Namespace) -> None:
    """Show graph statistics."""
    stats = kg.stats()
    print("\nKnowledge Graph Statistics:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


def main():
    parser = argparse.ArgumentParser(description="AI VC Knowledge Graph CLI")
    parser.add_argument("--graph", default=str(GRAPH_PATH), help="Path to graph.json")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # portfolio <firm>
    p_port = subparsers.add_parser("portfolio", help="Show firm's portfolio companies")
    p_port.add_argument("name", nargs="+", help="Firm name")

    # investors <company>
    p_inv = subparsers.add_parser("investors", help="Show company's investors")
    p_inv.add_argument("name", nargs="+", help="Company name")

    # co-investors <firm>
    p_co = subparsers.add_parser("co-investors", help="Show co-investors with a firm")
    p_co.add_argument("name", nargs="+", help="Firm name")

    # details <firm>
    p_det = subparsers.add_parser("details", help="Show full firm details")
    p_det.add_argument("name", nargs="+", help="Firm name")

    # search <term>
    p_search = subparsers.add_parser("search", help="Search for entities")
    p_search.add_argument("term", nargs="+", help="Search term")

    # stats
    subparsers.add_parser("stats", help="Show graph statistics")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    kg = KnowledgeGraph.load(args.graph)

    commands = {
        "portfolio": cmd_portfolio,
        "investors": cmd_investors,
        "co-investors": cmd_co_investors,
        "details": cmd_details,
        "search": cmd_search,
        "stats": cmd_stats,
    }
    commands[args.command](kg, args)


if __name__ == "__main__":
    main()
