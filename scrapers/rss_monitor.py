"""RSS feed monitor for AI VC news sources."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import feedparser

from scrapers.base import BaseScraper, ScrapedDeal, ScrapeResult

# Keywords that indicate a funding/investment article
FUNDING_KEYWORDS = [
    r"\braises?\b",
    r"\bfunding\b",
    r"\bseries [a-f]\b",
    r"\bseed round\b",
    r"\binvest(?:ment|ed|s|or)?\b",
    r"\bvaluation\b",
    r"\bunicorn\b",
    r"\bipo\b",
    r"\bacquir(?:e[ds]?|ition)\b",
    r"\bmerger\b",
    r"\b\$\d+[bmk]\b",
]

FUNDING_PATTERN = re.compile("|".join(FUNDING_KEYWORDS), re.IGNORECASE)


class RSSMonitor(BaseScraper):
    """Monitor RSS feeds for AI VC funding news."""

    def __init__(self, feeds: list[dict]) -> None:
        """Initialize with list of feed dicts (name, rss url)."""
        self.feeds = [f for f in feeds if f.get("rss")]

    @property
    def name(self) -> str:
        return "RSS Monitor"

    def scrape(self) -> ScrapeResult:
        """Fetch all RSS feeds, filter for funding articles."""
        result = ScrapeResult(source_name=self.name)

        for feed_info in self.feeds:
            feed_name = feed_info.get("name", "unknown")
            feed_url = feed_info["rss"]
            try:
                articles = self._fetch_feed(feed_url, feed_name)
                result.deals.extend(articles)
            except Exception as e:
                result.errors.append(f"Error fetching {feed_name}: {e}")

        return result

    def _fetch_feed(self, url: str, source_name: str) -> list[ScrapedDeal]:
        """Fetch a single RSS feed and return funding-related articles."""
        feed = feedparser.parse(url)
        articles = []

        for entry in feed.entries:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            link = entry.get("link", "")
            text = f"{title} {summary}"

            if FUNDING_PATTERN.search(text):
                # This is a funding-related article
                # We create a placeholder deal - LLM extractor will fill details
                deal = ScrapedDeal(
                    investor="",  # To be filled by LLM extractor
                    company="",
                    source_url=link,
                    raw_text=text[:2000],
                    confidence=0.5,  # Low confidence until LLM validates
                )
                articles.append(deal)

        return articles

    def fetch_articles(self) -> list[dict]:
        """Fetch funding-related articles (raw, for LLM extraction)."""
        result = self.scrape()
        return [
            {
                "source_url": d.source_url,
                "raw_text": d.raw_text,
            }
            for d in result.deals
        ]
