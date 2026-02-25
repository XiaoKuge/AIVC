#!/usr/bin/env python3
"""Curate AI VC deals from authoritative source articles.

Fetches a URL, extracts the article text, then uses an LLM to extract
structured deal data from the *real* article content (not hallucinated).

Each extracted deal includes a source_url pointing back to the original article.

Usage:
    python scripts/curate_deals.py <url> [<url2> ...]
    python scripts/curate_deals.py --file urls.txt
    python scripts/curate_deals.py --list  # show current curated deals
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aivc.extract import extract_deals, fetch_article

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEALS_PATH = DATA_DIR / "raw" / "curated_deals.json"


def load_existing_deals() -> list[dict]:
    """Load existing curated deals."""
    if DEALS_PATH.exists():
        with open(DEALS_PATH) as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    return []


def save_deals(deals: list[dict]) -> None:
    """Save deals to the curated deals file."""
    DEALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DEALS_PATH, "w") as f:
        json.dump(deals, f, indent=2, ensure_ascii=False)


def deduplicate(existing: list[dict], new_deals: list[dict]) -> list[dict]:
    """Return only new deals that don't already exist (by investor+company+round key)."""
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


def process_url(url: str, existing: list[dict]) -> list[dict]:
    """Fetch and extract deals from a single URL."""
    print(f"\n{'='*60}")
    print(f"Fetching: {url}")

    try:
        text = fetch_article(url)
    except Exception as e:
        print(f"  Error fetching URL: {e}")
        return []

    if not text or len(text) < 100:
        print(f"  Warning: Very little text extracted ({len(text)} chars). Skipping.")
        return []

    print(f"  Extracted {len(text)} chars of article text")
    print(f"  Sending to LLM for deal extraction...")

    try:
        deals = extract_deals(text, url)
    except Exception as e:
        print(f"  Error during LLM extraction: {e}")
        return []

    if not deals:
        print("  No deals found in article.")
        return []

    # Deduplicate against existing
    new_deals = deduplicate(existing, deals)
    skipped = len(deals) - len(new_deals)

    print(f"  Found {len(deals)} deals ({skipped} duplicates skipped)")
    for d in new_deals:
        amt = f" — {d['amount']}" if d["amount"] else ""
        rnd = f" ({d['round']})" if d["round"] else ""
        print(f"    + {d['investor']} -> {d['company']}{amt}{rnd}")

    return new_deals


def main():
    parser = argparse.ArgumentParser(description="Curate AI VC deals from source articles")
    parser.add_argument("urls", nargs="*", help="URLs to process")
    parser.add_argument("--file", "-f", help="File containing URLs (one per line)")
    parser.add_argument("--list", "-l", action="store_true", help="List current curated deals")
    parser.add_argument("--dry-run", action="store_true", help="Extract but don't save")
    args = parser.parse_args()

    if args.list:
        deals = load_existing_deals()
        print(f"\nCurated deals: {len(deals)}")
        for i, d in enumerate(deals, 1):
            amt = f" — {d['amount']}" if d.get("amount") else ""
            rnd = f" ({d['round']})" if d.get("round") else ""
            dt = f" [{d['date']}]" if d.get("date") else ""
            print(f"  {i:3d}. {d['investor']} -> {d['company']}{amt}{rnd}{dt}")
            if d.get("source_url"):
                print(f"       src: {d['source_url']}")
        return

    urls = list(args.urls)
    if args.file:
        with open(args.file) as f:
            urls.extend(line.strip() for line in f if line.strip() and not line.startswith("#"))

    if not urls:
        parser.print_help()
        sys.exit(1)

    existing = load_existing_deals()
    print(f"Existing curated deals: {len(existing)}")

    all_new = []
    for url in urls:
        new_deals = process_url(url, existing + all_new)
        all_new.extend(new_deals)

    if not all_new:
        print("\nNo new deals to add.")
        return

    print(f"\n{'='*60}")
    print(f"Total new deals extracted: {len(all_new)}")

    if args.dry_run:
        print("(Dry run — not saving)")
        return

    combined = existing + all_new
    save_deals(combined)
    print(f"Saved {len(combined)} total deals to {DEALS_PATH}")
    print("\nReview the output, then run: python scripts/import_deals.py")


if __name__ == "__main__":
    main()
