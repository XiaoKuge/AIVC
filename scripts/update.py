#!/usr/bin/env python3
"""Unified daily update pipeline for the AI VC knowledge graph.

Modes:
    python scripts/update.py --fetch          # RSS → raw articles (no LLM)
    python scripts/update.py --approve        # Import staged deals into graph
    python scripts/update.py --list           # Show pending staged deals
    python scripts/update.py --dry-run        # Preview without saving anything

Pipeline:
    1. Fetch: RSS feeds → filter funding articles → save raw text (no LLM)
    2. Extract: Done by Claude Code during interactive sessions
    3. Stage: Extracted deals written to data/staging/pending_deals.json
    4. Approve: staged deals → graph merge → snapshot → save → regenerate viz
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aivc.graph import KnowledgeGraph
from aivc.ingest import get_news_sources, load_aliases, normalize_name
from aivc.models import Company, Deal, VCFirm
from aivc.state import PipelineState
from scrapers.rss_monitor import RSSMonitor

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GRAPH_PATH = DATA_DIR / "graph.json"
STAGING_PATH = DATA_DIR / "staging" / "pending_deals.json"
RAW_ARTICLES_PATH = DATA_DIR / "staging" / "raw_articles.json"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
CHANGELOG_PATH = DATA_DIR / "changelog.json"


# ── Staging I/O ─────────────────────────────────────────────


def load_staging() -> list[dict]:
    if STAGING_PATH.exists():
        with open(STAGING_PATH) as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    return []


def save_staging(deals: list[dict]) -> None:
    STAGING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STAGING_PATH, "w") as f:
        json.dump(deals, f, indent=2, ensure_ascii=False)


def deduplicate(existing: list[dict], new_deals: list[dict]) -> list[dict]:
    """Return only new deals not already in existing (by investor+company+round)."""
    seen = set()
    for d in existing:
        key = (d["investor"].lower(), d["company"].lower(), d.get("round", "").lower())
        seen.add(key)

    unique = []
    for d in new_deals:
        key = (d["investor"].lower(), d["company"].lower(), d.get("round", "").lower())
        if key not in seen:
            unique.append(d)
            seen.add(key)
    return unique


# ── Fetch Phase (raw articles, no LLM) ───────────────────────


def load_raw_articles() -> list[dict]:
    if RAW_ARTICLES_PATH.exists():
        with open(RAW_ARTICLES_PATH) as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    return []


def save_raw_articles(articles: list[dict]) -> None:
    RAW_ARTICLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RAW_ARTICLES_PATH, "w") as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)


def fetch_rss_raw(state: PipelineState) -> list[dict]:
    """Fetch RSS feeds and return raw articles (no LLM extraction)."""
    print("Fetching RSS feeds...")
    news_sources = get_news_sources()
    rss = RSSMonitor(news_sources)
    articles = rss.fetch_articles()

    # Filter out already-processed URLs
    new_articles = [a for a in articles if not state.is_processed(a["source_url"])]
    print(f"  RSS articles: {len(articles)} total, {len(new_articles)} new")

    if not new_articles:
        print("  No new articles to process.")
        return []

    raw: list[dict] = []
    for article in new_articles:
        url = article["source_url"]
        raw_text = article.get("raw_text", "")

        if not raw_text or len(raw_text) < 100:
            print(f"  Skipping (insufficient text): {url}")
            state.mark_processed(url, deals_found=0)
            state.save()
            continue

        raw.append({
            "source_url": url,
            "raw_text": raw_text,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        state.mark_processed(url, deals_found=0)
        state.save()
        print(f"  Fetched: {url} ({len(raw_text)} chars)")

    return raw


# ── Stage Phase ──────────────────────────────────────────────


def stage_deals(new_deals: list[dict], dry_run: bool = False) -> int:
    """Append new deals to staging, deduplicating against existing staged deals."""
    existing = load_staging()
    unique = deduplicate(existing, new_deals)

    if not unique:
        print("\nNo new unique deals to stage.")
        return 0

    print(f"\nStaging {len(unique)} new deals ({len(new_deals) - len(unique)} duplicates skipped)")
    for d in unique:
        amt = f" — {d['amount']}" if d.get("amount") else ""
        rnd = f" ({d['round']})" if d.get("round") else ""
        print(f"  + {d['investor']} -> {d['company']}{amt}{rnd}")

    if not dry_run:
        save_staging(existing + unique)

    return len(unique)


# ── Approve Phase ────────────────────────────────────────────


def approve_staged(dry_run: bool = False) -> dict:
    """Import staged deals into the graph, then clear staging."""
    staged = load_staging()
    if not staged:
        print("No staged deals to approve.")
        return {"deals_imported": 0}

    print(f"Approving {len(staged)} staged deals...")

    # Load graph
    if GRAPH_PATH.exists():
        kg = KnowledgeGraph.load(GRAPH_PATH)
    else:
        print("No existing graph.json found. Run seed.py first.")
        return {"deals_imported": 0}

    prev_stats = kg.stats()
    aliases = load_aliases()

    for d in staged:
        investor = normalize_name(d["investor"], aliases)
        company = normalize_name(d["company"], aliases)
        source = f"pipeline:{d.get('source_url', '')}" if d.get("source_url") else "pipeline"

        kg.add_firm(VCFirm(name=investor, source=source))
        kg.add_company(Company(
            name=company,
            sector=d.get("company_sector", ""),
            source=source,
        ))
        kg.add_investment(investor, company, Deal(
            amount=d.get("amount", ""),
            round=d.get("round", ""),
            date=d.get("date", ""),
            source=source,
        ))

    new_stats = kg.stats()
    summary = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "deals_imported": len(staged),
        "nodes_added": new_stats["total_nodes"] - prev_stats["total_nodes"],
        "edges_added": new_stats["total_edges"] - prev_stats["total_edges"],
    }

    if dry_run:
        print(f"\nDry run — would import {len(staged)} deals:")
        print(f"  +{summary['nodes_added']} nodes, +{summary['edges_added']} edges")
        return summary

    # Snapshot before saving
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    shutil.copy2(GRAPH_PATH, SNAPSHOTS_DIR / f"graph_{ts}.json")

    # Save graph
    kg.save(GRAPH_PATH)
    print(f"  Graph saved (+{summary['nodes_added']} nodes, +{summary['edges_added']} edges)")

    # Append to changelog
    _append_changelog(summary)

    # Clear staging
    save_staging([])
    print("  Staging cleared.")

    # Regenerate visualization
    print("  Regenerating visualization...")
    try:
        from viz.generate import generate_html

        generate_html()
        print("  Visualization updated.")
    except Exception as e:
        print(f"  Warning: visualization generation failed: {e}")

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


# ── CLI ──────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Unified AI VC knowledge graph update pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python scripts/update.py --fetch          # RSS → raw articles (no LLM)
  python scripts/update.py --approve        # Import staged → graph
  python scripts/update.py --list           # View staged deals
""",
    )
    parser.add_argument("--fetch", action="store_true",
                        help="Fetch RSS articles and save raw text (no LLM)")
    parser.add_argument("--approve", action="store_true",
                        help="Import staged deals into the graph")
    parser.add_argument("--list", action="store_true",
                        help="List currently staged deals")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without saving")
    args = parser.parse_args()

    # List mode
    if args.list:
        staged = load_staging()
        print(f"\nStaged deals: {len(staged)}")
        for i, d in enumerate(staged, 1):
            amt = f" — {d['amount']}" if d.get("amount") else ""
            rnd = f" ({d['round']})" if d.get("round") else ""
            dt = f" [{d['date']}]" if d.get("date") else ""
            print(f"  {i:3d}. {d['investor']} -> {d['company']}{amt}{rnd}{dt}")
        return

    # Approve mode
    if args.approve:
        approve_staged(dry_run=args.dry_run)
        return

    # Fetch mode
    if args.fetch:
        state = PipelineState()
        new_articles = fetch_rss_raw(state)

        if not new_articles:
            print("\nNo new articles fetched.")
            return

        if args.dry_run:
            print(f"\nDry run — would save {len(new_articles)} raw articles:")
            for a in new_articles:
                print(f"  {a['source_url']} ({len(a['raw_text'])} chars)")
            return

        # Append to existing raw articles
        existing = load_raw_articles()
        existing_urls = {a["source_url"] for a in existing}
        added = [a for a in new_articles if a["source_url"] not in existing_urls]
        save_raw_articles(existing + added)

        url_stats = state.stats()
        print(f"\nSaved {len(added)} new raw articles to {RAW_ARTICLES_PATH}")
        print(f"Pipeline state: {url_stats['total_processed']} URLs processed")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
