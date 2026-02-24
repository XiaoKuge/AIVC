#!/usr/bin/env python3
"""Batch-enrich Company nodes missing metadata (sector, website, founded_year).

Uses LLM to look up factual company attributes for nodes that are missing them.
This is lower risk than deal extraction since these are verifiable company facts.

Usage:
    python scripts/enrich_batch.py
    python scripts/enrich_batch.py --limit 20
    python scripts/enrich_batch.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aivc.graph import KnowledgeGraph

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GRAPH_PATH = DATA_DIR / "graph.json"

SYSTEM_PROMPT = """You are a factual company metadata assistant. Given a list of AI/tech company names, provide accurate metadata for each.

Return a JSON object where keys are the company names (exactly as provided) and values are objects with:
- sector: The company's AI sub-sector (e.g. "Foundation Models", "AI Code", "AI Infrastructure", "AI Healthcare", "Robotics", "Autonomous Vehicles", "AI Chips", "AI Security", "AI Video", "AI Audio", "Data & AI Platform")
- website: The company's primary domain (e.g. "openai.com"), without https://
- founded_year: Year the company was founded (integer), or null if unknown

IMPORTANT: Only provide information you are confident about. Use null for unknown values.
Do NOT guess or fabricate data. If you're unsure about a company, still include it but use null for uncertain fields."""

ENRICH_PROMPT = """Provide metadata for these AI/tech companies:

{companies}

Return ONLY valid JSON, no markdown fences."""


def find_companies_to_enrich(kg: KnowledgeGraph) -> list[tuple[str, dict]]:
    """Find Company nodes missing sector, website, or founded_year."""
    to_enrich = []
    for nid, attrs in kg.companies():
        missing_sector = not attrs.get("sector")
        missing_website = not attrs.get("website")
        missing_year = not attrs.get("founded_year")
        if missing_sector or missing_website or missing_year:
            to_enrich.append((nid, attrs))
    return to_enrich


def enrich_batch_llm(company_names: list[str]) -> dict[str, dict]:
    """Use LLM to get metadata for a batch of company names."""
    provider = _detect_provider()
    companies_text = "\n".join(f"- {name}" for name in company_names)

    if provider == "anthropic":
        return _enrich_anthropic(companies_text)
    elif provider == "openai":
        return _enrich_openai(companies_text)
    else:
        print("Error: Set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable.")
        sys.exit(1)


def _detect_provider() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return ""


def _enrich_anthropic(companies_text: str) -> dict[str, dict]:
    import anthropic

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": ENRICH_PROMPT.format(companies=companies_text)},
        ],
    )
    return _parse_response(message.content[0].text)


def _enrich_openai(companies_text: str) -> dict[str, dict]:
    from openai import OpenAI

    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": ENRICH_PROMPT.format(companies=companies_text)},
        ],
        max_tokens=4096,
        temperature=0,
    )
    return _parse_response(response.choices[0].message.content or "")


def _parse_response(response_text: str) -> dict[str, dict]:
    """Parse LLM JSON response."""
    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    data = json.loads(text)
    if not isinstance(data, dict):
        return {}
    return data


def apply_enrichment(kg: KnowledgeGraph, enrichment: dict[str, dict], companies: list[tuple[str, dict]]) -> int:
    """Apply enrichment data to graph nodes. Returns count of updated nodes."""
    # Build name-to-nid map
    name_to_nid = {}
    for nid, attrs in companies:
        name_to_nid[attrs.get("name", "")] = nid

    updated = 0
    for company_name, metadata in enrichment.items():
        nid = name_to_nid.get(company_name)
        if not nid or nid not in kg.g:
            continue

        node = kg.g.nodes[nid]
        changed = False

        if metadata.get("sector") and not node.get("sector"):
            node["sector"] = metadata["sector"]
            changed = True
        if metadata.get("website") and not node.get("website"):
            node["website"] = metadata["website"]
            changed = True
        if metadata.get("founded_year") and not node.get("founded_year"):
            node["founded_year"] = metadata["founded_year"]
            changed = True

        if changed:
            updated += 1

    return updated


def main():
    parser = argparse.ArgumentParser(description="Batch-enrich company nodes with metadata")
    parser.add_argument("--limit", "-n", type=int, default=50,
                        help="Max companies per LLM batch (default: 50)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be enriched without saving")
    args = parser.parse_args()

    if not GRAPH_PATH.exists():
        print(f"Graph not found: {GRAPH_PATH}")
        sys.exit(1)

    kg = KnowledgeGraph.load(GRAPH_PATH)
    to_enrich = find_companies_to_enrich(kg)

    if not to_enrich:
        print("All Company nodes already have complete metadata.")
        return

    print(f"Found {len(to_enrich)} companies missing metadata")

    # Process in batches
    batch = to_enrich[:args.limit]
    company_names = [attrs.get("name", nid) for nid, attrs in batch]

    print(f"Enriching batch of {len(company_names)} companies...")
    for name in company_names:
        print(f"  - {name}")

    enrichment = enrich_batch_llm(company_names)
    print(f"\nLLM returned metadata for {len(enrichment)} companies")

    if args.dry_run:
        for name, meta in enrichment.items():
            print(f"  {name}: {meta}")
        print("\n(Dry run — graph not saved)")
        return

    updated = apply_enrichment(kg, enrichment, batch)
    print(f"Updated {updated} company nodes")

    kg.save(GRAPH_PATH)
    print(f"Graph saved to {GRAPH_PATH}")

    remaining = len(to_enrich) - len(batch)
    if remaining > 0:
        print(f"\n{remaining} companies still need enrichment. Run again to process more.")


if __name__ == "__main__":
    main()
