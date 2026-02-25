"""LLM-assisted structured extraction of deal data from articles.

Delegates to aivc.extract for the actual LLM calls.
This module preserves the ScrapedDeal interface for backward compatibility.
"""

from __future__ import annotations

from aivc.extract import extract_deals as _extract_deals
from scrapers.base import ScrapedDeal


class LLMExtractor:
    """Extract structured deal data from article text using LLM.

    Provider is auto-detected from environment variables:
      - ANTHROPIC_API_KEY -> uses Anthropic (claude-sonnet)
      - OPENAI_API_KEY    -> uses OpenAI (gpt-4o)
    """

    def extract_deals(self, text: str, source_url: str = "") -> list[ScrapedDeal]:
        """Extract deals from article text using LLM."""
        dicts = _extract_deals(text, source_url)
        return [
            ScrapedDeal(
                investor=d["investor"],
                company=d["company"],
                amount=d.get("amount", ""),
                round=d.get("round", ""),
                date=d.get("date", ""),
                source_url=d.get("source_url", source_url),
                confidence=0.8,
            )
            for d in dicts
        ]

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
