"""Tests for XLSX ingestion."""

from pathlib import Path

import pytest

from aivc.ingest import ingest_xlsx, normalize_name, parse_portfolio_list, get_news_sources, XLSX_PATH


class TestParseHelpers:
    def test_parse_portfolio_list(self):
        result = parse_portfolio_list("OpenAI, Databricks, Mistral")
        assert result == ["OpenAI", "Databricks", "Mistral"]

    def test_parse_portfolio_list_empty(self):
        assert parse_portfolio_list("") == []
        assert parse_portfolio_list(None) == []

    def test_normalize_name(self):
        aliases = {"open ai": "OpenAI", "hf": "Hugging Face"}
        assert normalize_name("open ai", aliases) == "OpenAI"
        assert normalize_name("hf", aliases) == "Hugging Face"
        assert normalize_name("Unknown", aliases) == "Unknown"

    def test_normalize_name_strips(self):
        assert normalize_name("  OpenAI  ") == "OpenAI"


@pytest.mark.skipif(not XLSX_PATH.exists(), reason="XLSX file not available")
class TestIngestXLSX:
    def test_ingest_produces_firms(self):
        kg = ingest_xlsx()
        firms = kg.firms()
        assert len(firms) >= 80  # At least 80 firms from the 81 rows

    def test_ingest_produces_companies(self):
        kg = ingest_xlsx()
        companies = kg.companies()
        assert len(companies) >= 100  # Many portfolio companies

    def test_ingest_produces_people(self):
        kg = ingest_xlsx()
        people = kg.people()
        assert len(people) == 23

    def test_ingest_has_a16z(self):
        kg = ingest_xlsx()
        assert "andreessen-horowitz-(a16z)" in kg.g
        attrs = kg.g.nodes["andreessen-horowitz-(a16z)"]
        assert "a16z" in attrs["name"]

    def test_ingest_has_investments(self):
        kg = ingest_xlsx()
        stats = kg.stats()
        assert stats["investments"] > 200

    def test_news_sources(self):
        sources = get_news_sources()
        assert len(sources) >= 25
        assert any(s["name"] == "TechCrunch AI" for s in sources)
