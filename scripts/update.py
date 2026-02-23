#!/usr/bin/env python3
"""Run incremental update cycle: fetch RSS -> extract -> validate -> merge -> save."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aivc.graph import KnowledgeGraph
from aivc.ingest import get_news_sources
from aivc.models import Company, Deal, VCFirm
from scrapers.llm_extractor import LLMExtractor
from scrapers.rss_monitor import RSSMonitor

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GRAPH_PATH = DATA_DIR / "graph.json"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
CHANGELOG_PATH = DATA_DIR / "changelog.json"


def run_update(dry_run: bool = False) -> dict:
    """Run a full incremental update cycle.

    Returns a summary dict of what was added/modified.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary = {
        "timestamp": timestamp,
        "articles_found": 0,
        "deals_extracted": 0,
        "nodes_added": 0,
        "edges_added": 0,
        "errors": [],
    }

    # Load existing graph
    if GRAPH_PATH.exists():
        kg = KnowledgeGraph.load(GRAPH_PATH)
    else:
        print("No existing graph.json found. Run seed.py first.")
        return summary

    prev_stats = kg.stats()

    # Step 1: Fetch RSS feeds
    print("Fetching RSS feeds...")
    news_sources = get_news_sources()
    rss = RSSMonitor(news_sources)
    articles = rss.fetch_articles()
    summary["articles_found"] = len(articles)
    print(f"  Found {len(articles)} funding-related articles")

    if not articles:
        print("No new articles found. Done.")
        return summary

    # Step 2: Extract structured deals via LLM
    print("Extracting deals via LLM...")
    extractor = LLMExtractor()
    deals = extractor.extract_from_articles(articles)
    summary["deals_extracted"] = len(deals)
    print(f"  Extracted {len(deals)} deals")

    if not deals:
        print("No deals extracted. Done.")
        return summary

    # Step 3: Merge into graph
    print("Merging into knowledge graph...")
    for deal in deals:
        if deal.confidence < 0.5:
            continue
        # Ensure firm exists
        kg.add_firm(VCFirm(name=deal.investor, source=deal.source_url))
        kg.add_company(Company(name=deal.company, source=deal.source_url))
        kg.add_investment(
            deal.investor,
            deal.company,
            Deal(
                amount=deal.amount,
                round=deal.round,
                date=deal.date,
                source=deal.source_url,
            ),
        )

    new_stats = kg.stats()
    summary["nodes_added"] = new_stats["total_nodes"] - prev_stats["total_nodes"]
    summary["edges_added"] = new_stats["total_edges"] - prev_stats["total_edges"]

    if dry_run:
        print("\nDry run - not saving changes.")
        print(f"Would add {summary['nodes_added']} nodes, {summary['edges_added']} edges")
        return summary

    # Step 4: Save snapshot and updated graph
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_name = f"graph_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    shutil.copy2(GRAPH_PATH, SNAPSHOTS_DIR / snapshot_name)

    kg.save(GRAPH_PATH)
    print(f"  Saved updated graph ({summary['nodes_added']} new nodes, {summary['edges_added']} new edges)")

    # Step 5: Append to changelog
    _append_changelog(summary)

    # Step 6: Regenerate visualization
    print("Regenerating visualization...")
    try:
        from viz.generate import generate_html
        generate_html()
        print("  Visualization updated.")
    except Exception as e:
        summary["errors"].append(f"Viz generation failed: {e}")
        print(f"  Warning: visualization generation failed: {e}")

    print("\nUpdate complete.")
    print(f"  Articles: {summary['articles_found']}")
    print(f"  Deals extracted: {summary['deals_extracted']}")
    print(f"  New nodes: {summary['nodes_added']}")
    print(f"  New edges: {summary['edges_added']}")

    return summary


def _append_changelog(entry: dict) -> None:
    """Append an update entry to the changelog."""
    changelog = []
    if CHANGELOG_PATH.exists():
        with open(CHANGELOG_PATH) as f:
            changelog = json.load(f)
    changelog.append(entry)
    with open(CHANGELOG_PATH, "w") as f:
        json.dump(changelog, f, indent=2, sort_keys=True)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run incremental update")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without saving")
    args = parser.parse_args()

    run_update(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
