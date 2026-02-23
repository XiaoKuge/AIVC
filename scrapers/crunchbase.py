"""Crunchbase API scraper (future implementation)."""

from __future__ import annotations

from scrapers.base import BaseScraper, ScrapeResult


class CrunchbaseScraper(BaseScraper):
    """Fetch historical funding data from Crunchbase API.

    Requires a Crunchbase API key. Not yet implemented.
    """

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    @property
    def name(self) -> str:
        return "Crunchbase"

    def scrape(self) -> ScrapeResult:
        """Placeholder for Crunchbase API integration."""
        return ScrapeResult(
            source_name=self.name,
            errors=["Crunchbase scraper not yet implemented"],
        )
