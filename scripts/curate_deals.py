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
import os
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEALS_PATH = DATA_DIR / "raw" / "curated_deals.json"

SYSTEM_PROMPT = """You are an expert AI VC deal extractor. Given a news article, extract EVERY AI-related venture capital deal mentioned.

Return a JSON array of deals. Each deal MUST have:
- investor: The lead VC firm or investor name (string). If multiple investors, use the lead.
- company: The startup/company receiving investment (string)
- amount: Deal size if mentioned, e.g. "$500M", "$6.6B" (string, "" if unknown)
- round: Funding round, e.g. "Series A", "Series B", "Seed" (string, "" if unknown)
- date: Date as YYYY-MM-DD or YYYY-MM or YYYY (string, "" if unknown)
- source_url: Will be provided separately, leave as ""
- company_sector: AI sub-sector, e.g. "Foundation Models", "AI Code", "AI Infrastructure", "AI Healthcare", "Robotics", "Autonomous Vehicles" (string, "" if unknown)

IMPORTANT RULES:
1. Only extract deals that are EXPLICITLY mentioned in the article text
2. Do NOT fabricate or hallucinate any deals - if unsure, skip it
3. For multi-investor rounds, list the LEAD investor. If no lead is specified, use the first-mentioned investor
4. Include ALL deals mentioned, even briefly
5. If the same company has multiple rounds mentioned, create separate entries
6. Return ONLY valid JSON, no markdown fences or explanation"""

EXTRACT_PROMPT = """Extract ALL AI VC investment deals from this article:

---
{text}
---

Return ONLY a valid JSON array of deal objects."""


def fetch_article(url: str) -> str:
    """Fetch a URL and extract article text."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove non-content elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    # Try to find the main article content
    article = soup.find("article") or soup.find("main") or soup.find("body")
    if article is None:
        return ""

    text = article.get_text(separator="\n", strip=True)
    # Collapse multiple newlines
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def extract_deals_llm(text: str, source_url: str) -> list[dict]:
    """Use LLM to extract structured deals from article text."""
    # Truncate very long articles to fit context
    max_chars = 12000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[Article truncated...]"

    provider = _detect_provider()
    if provider == "anthropic":
        return _extract_anthropic(text, source_url)
    elif provider == "openai":
        return _extract_openai(text, source_url)
    else:
        print("Error: Set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable.")
        sys.exit(1)


def _detect_provider() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return ""


def _extract_anthropic(text: str, source_url: str) -> list[dict]:
    import anthropic

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": EXTRACT_PROMPT.format(text=text)},
        ],
    )
    return _parse_response(message.content[0].text, source_url)


def _extract_openai(text: str, source_url: str) -> list[dict]:
    from openai import OpenAI

    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": EXTRACT_PROMPT.format(text=text)},
        ],
        max_tokens=4096,
        temperature=0,
    )
    return _parse_response(response.choices[0].message.content or "", source_url)


def _parse_response(response_text: str, source_url: str) -> list[dict]:
    """Parse the LLM JSON response and attach source_url."""
    # Strip markdown code fences if present
    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    deals = json.loads(text)
    if not isinstance(deals, list):
        return []

    # Attach source_url and validate
    valid = []
    for d in deals:
        if not d.get("investor") or not d.get("company"):
            continue
        d["source_url"] = source_url
        # Normalize fields
        for field in ("amount", "round", "date", "company_sector"):
            if field not in d:
                d[field] = ""
        valid.append({
            "investor": d["investor"].strip(),
            "company": d["company"].strip(),
            "amount": d.get("amount", "").strip(),
            "round": d.get("round", "").strip(),
            "date": d.get("date", "").strip(),
            "source_url": d["source_url"],
            "company_sector": d.get("company_sector", "").strip(),
        })
    return valid


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
        deals = extract_deals_llm(text, url)
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
