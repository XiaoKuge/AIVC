"""Unified LLM-based deal extraction from article text.

Merges the extraction logic from scrapers/llm_extractor.py and
scripts/curate_deals.py into a single module with:
- Better prompt (sector extraction, anti-hallucination rules)
- Retry logic with exponential backoff
- Safe JSON parsing (no crashes on malformed LLM output)
- Full article fetching from URLs
"""

from __future__ import annotations

import json
import os
import time

import requests
from bs4 import BeautifulSoup

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

MAX_ARTICLE_CHARS = 12000
MAX_RETRIES = 2
RETRY_DELAY = 3  # seconds


def detect_provider() -> tuple[str, str]:
    """Return (provider_name, api_key) from environment variables."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", os.environ["ANTHROPIC_API_KEY"]
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", os.environ["OPENAI_API_KEY"]
    return "", ""


def fetch_article(url: str) -> str:
    """Fetch a URL and extract article text using BeautifulSoup."""
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
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def extract_deals(text: str, source_url: str = "") -> list[dict]:
    """Extract deals from article text via LLM.

    Returns list of dicts with keys:
        investor, company, amount, round, date, source_url, company_sector
    """
    provider, api_key = detect_provider()
    if not api_key:
        print("Warning: No API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY.")
        return []

    # Truncate very long articles
    if len(text) > MAX_ARTICLE_CHARS:
        text = text[:MAX_ARTICLE_CHARS] + "\n\n[Article truncated...]"

    response_text = _call_llm(text, provider, api_key)
    if not response_text:
        return []

    return _parse_response(response_text, source_url)


def _call_llm(text: str, provider: str, api_key: str) -> str:
    """Call LLM API with retry logic. Returns raw response text."""
    prompt = EXTRACT_PROMPT.format(text=text)

    for attempt in range(MAX_RETRIES + 1):
        try:
            if provider == "anthropic":
                return _call_anthropic(prompt, api_key)
            else:
                return _call_openai(prompt, api_key)
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = RETRY_DELAY * (attempt + 1)
                print(f"  LLM call failed (attempt {attempt + 1}): {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  LLM call failed after {MAX_RETRIES + 1} attempts: {e}")
                return ""
    return ""


def _call_anthropic(prompt: str, api_key: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def _call_openai(prompt: str, api_key: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4096,
        temperature=0,
    )
    return response.choices[0].message.content or ""


def _parse_response(response_text: str, source_url: str) -> list[dict]:
    """Parse LLM JSON response with safe error handling."""
    text = response_text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        deals = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  Warning: Failed to parse LLM response as JSON: {e}")
        return []

    if not isinstance(deals, list):
        return []

    valid = []
    for d in deals:
        if not d.get("investor") or not d.get("company"):
            continue
        valid.append({
            "investor": d["investor"].strip(),
            "company": d["company"].strip(),
            "amount": d.get("amount", "").strip(),
            "round": d.get("round", "").strip(),
            "date": d.get("date", "").strip(),
            "source_url": source_url,
            "company_sector": d.get("company_sector", "").strip(),
        })
    return valid
