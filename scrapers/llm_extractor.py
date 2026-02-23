"""LLM-assisted structured extraction of deal data from articles."""

from __future__ import annotations

import json
import os

from scrapers.base import ScrapedDeal

SYSTEM_PROMPT = """You are an AI VC deal extractor. Given a news article or text snippet, extract structured deal information.

Return a JSON array of deals. Each deal should have these fields:
- investor: Name of the VC firm or investor (string)
- company: Name of the company receiving investment (string)
- amount: Deal amount if mentioned, e.g. "$50M" (string, empty if unknown)
- round: Funding round if mentioned, e.g. "Series A" (string, empty if unknown)
- date: Date if mentioned, in YYYY-MM-DD format (string, empty if unknown)

If no deals are found, return an empty array: []
Only extract deals where you are confident about at least the investor and company names.
"""

EXTRACT_PROMPT = """Extract AI VC investment deals from this text:

---
{text}
---

Source URL: {url}

Return ONLY valid JSON array of deals."""

# Provider detection: check which API key is available
PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"


def _detect_provider(api_key: str | None, provider: str | None) -> tuple[str, str]:
    """Detect which LLM provider to use based on explicit choice or env vars.

    Returns (provider, api_key).
    """
    if provider == PROVIDER_OPENAI or (not provider and not api_key and os.environ.get("OPENAI_API_KEY")):
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        return PROVIDER_OPENAI, key

    if provider == PROVIDER_ANTHROPIC or (not provider and not api_key and os.environ.get("ANTHROPIC_API_KEY")):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        return PROVIDER_ANTHROPIC, key

    # Fallback: check both env vars
    if os.environ.get("OPENAI_API_KEY"):
        return PROVIDER_OPENAI, os.environ["OPENAI_API_KEY"]
    if os.environ.get("ANTHROPIC_API_KEY"):
        return PROVIDER_ANTHROPIC, os.environ["ANTHROPIC_API_KEY"]

    return "", api_key or ""


class LLMExtractor:
    """Extract structured deal data from article text using OpenAI or Anthropic API.

    Provider is auto-detected from environment variables:
      - OPENAI_API_KEY  -> uses OpenAI (gpt-4o)
      - ANTHROPIC_API_KEY -> uses Anthropic (claude-sonnet)

    You can also pass provider="openai" or provider="anthropic" explicitly.
    """

    def __init__(self, api_key: str | None = None, provider: str | None = None) -> None:
        self.provider, self.api_key = _detect_provider(api_key, provider)

    def extract_deals(self, text: str, source_url: str = "") -> list[ScrapedDeal]:
        """Extract deals from article text using LLM."""
        if not self.api_key:
            print("No API key found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY.")
            return []

        if self.provider == PROVIDER_OPENAI:
            return self._extract_openai(text, source_url)
        else:
            return self._extract_anthropic(text, source_url)

    def _extract_openai(self, text: str, source_url: str) -> list[ScrapedDeal]:
        """Extract deals using OpenAI API."""
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": EXTRACT_PROMPT.format(text=text[:3000], url=source_url),
                    },
                ],
                max_tokens=1024,
                temperature=0,
            )

            response_text = response.choices[0].message.content or ""
            return self._parse_deals(response_text, source_url)

        except Exception as e:
            print(f"OpenAI extraction error: {e}")
            return []

    def _extract_anthropic(self, text: str, source_url: str) -> list[ScrapedDeal]:
        """Extract deals using Anthropic API."""
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.api_key)
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": EXTRACT_PROMPT.format(text=text[:3000], url=source_url),
                    }
                ],
            )

            response_text = message.content[0].text
            return self._parse_deals(response_text, source_url)

        except Exception as e:
            print(f"Anthropic extraction error: {e}")
            return []

    def _parse_deals(self, response_text: str, source_url: str) -> list[ScrapedDeal]:
        """Parse LLM response JSON into ScrapedDeal objects."""
        deals_raw = json.loads(response_text)
        deals = []
        for d in deals_raw:
            if d.get("investor") and d.get("company"):
                deals.append(
                    ScrapedDeal(
                        investor=d["investor"],
                        company=d["company"],
                        amount=d.get("amount", ""),
                        round=d.get("round", ""),
                        date=d.get("date", ""),
                        source_url=source_url,
                        confidence=0.8,
                    )
                )
        return deals

    def extract_from_articles(self, articles: list[dict]) -> list[ScrapedDeal]:
        """Extract deals from multiple articles."""
        all_deals = []
        for article in articles:
            deals = self.extract_deals(
                text=article.get("raw_text", ""),
                source_url=article.get("source_url", ""),
            )
            all_deals.extend(deals)
        return all_deals
