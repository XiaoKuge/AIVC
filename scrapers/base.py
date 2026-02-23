"""Base scraper abstract class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ScrapedDeal:
    """A structured deal extracted from a source."""

    investor: str
    company: str
    amount: str = ""
    round: str = ""
    date: str = ""
    source_url: str = ""
    confidence: float = 1.0
    raw_text: str = ""


@dataclass
class ScrapeResult:
    """Result of a scrape run."""

    deals: list[ScrapedDeal] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    source_name: str = ""


class BaseScraper(ABC):
    """Abstract base class for all scrapers."""

    @abstractmethod
    def scrape(self) -> ScrapeResult:
        """Run the scraper and return results."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this scraper."""
        ...
