"""Per-firm website scrapers (future implementation)."""

from __future__ import annotations

from scrapers.base import BaseScraper, ScrapeResult


class VCWebsiteScraper(BaseScraper):
    """Scrape portfolio pages from VC firm websites.

    Targets like a16z.com/portfolio, sequoiacap.com/companies, etc.
    Not yet implemented.
    """

    def __init__(self, firm_name: str, portfolio_url: str) -> None:
        self.firm_name = firm_name
        self.portfolio_url = portfolio_url

    @property
    def name(self) -> str:
        return f"VC Website: {self.firm_name}"

    def scrape(self) -> ScrapeResult:
        """Placeholder for VC website scraping."""
        return ScrapeResult(
            source_name=self.name,
            errors=[f"VC website scraper for {self.firm_name} not yet implemented"],
        )
