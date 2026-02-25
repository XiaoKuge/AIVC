"""Persistent state management for the update pipeline.

Tracks which URLs have been processed to avoid redundant LLM API calls
across pipeline runs. State is saved after each URL for crash recovery.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent.parent / "data" / "state"
PROCESSED_URLS_PATH = STATE_DIR / "processed_urls.json"


class PipelineState:
    """Track which URLs have been processed to avoid re-extraction."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else PROCESSED_URLS_PATH
        self.processed: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            with open(self._path) as f:
                self.processed = json.load(f)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self.processed, f, indent=2, sort_keys=True)

    def is_processed(self, url: str) -> bool:
        return url in self.processed

    def mark_processed(self, url: str, deals_found: int = 0) -> None:
        self.processed[url] = {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "deals_found": deals_found,
        }

    def filter_new_urls(self, urls: list[str]) -> list[str]:
        return [u for u in urls if not self.is_processed(u)]

    def stats(self) -> dict[str, int]:
        total = len(self.processed)
        with_deals = sum(1 for v in self.processed.values() if v.get("deals_found", 0) > 0)
        return {"total_processed": total, "with_deals": with_deals}
