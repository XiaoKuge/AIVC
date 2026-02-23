"""Tests for query functions."""

import pytest

from aivc.graph import KnowledgeGraph
from aivc.models import Company, Deal, Person, PartnerEdge, VCFirm
from aivc.query import co_investors, investors, portfolio, search


def _make_test_graph() -> KnowledgeGraph:
    """Create a small test graph for query tests."""
    kg = KnowledgeGraph()

    # Firms
    kg.add_firm(VCFirm(name="Alpha VC"))
    kg.add_firm(VCFirm(name="Beta Capital"))
    kg.add_firm(VCFirm(name="Gamma Ventures"))

    # Companies
    kg.add_company(Company(name="AI Startup"))
    kg.add_company(Company(name="ML Corp"))
    kg.add_company(Company(name="Data Inc"))

    # Investments
    kg.add_investment("Alpha VC", "AI Startup", Deal(amount="$10M"))
    kg.add_investment("Alpha VC", "ML Corp", Deal(amount="$5M"))
    kg.add_investment("Beta Capital", "AI Startup", Deal(amount="$20M"))
    kg.add_investment("Beta Capital", "Data Inc", Deal(amount="$15M"))
    kg.add_investment("Gamma Ventures", "ML Corp", Deal(amount="$8M"))

    # People
    kg.add_person(Person(name="Alice Fund", title="GP"))
    kg.add_partner("Alice Fund", "Alpha VC", PartnerEdge(title="GP"))

    return kg


class TestPortfolio:
    def test_basic_portfolio(self):
        kg = _make_test_graph()
        result = portfolio(kg, "Alpha VC")
        names = [r["name"] for r in result]
        assert "AI Startup" in names
        assert "ML Corp" in names
        assert len(result) == 2

    def test_portfolio_not_found(self):
        kg = _make_test_graph()
        result = portfolio(kg, "Nonexistent VC")
        assert result == []


class TestInvestors:
    def test_basic_investors(self):
        kg = _make_test_graph()
        result = investors(kg, "AI Startup")
        names = [r["name"] for r in result]
        assert "Alpha VC" in names
        assert "Beta Capital" in names
        assert len(result) == 2


class TestCoInvestors:
    def test_basic_co_investors(self):
        kg = _make_test_graph()
        result = co_investors(kg, "Alpha VC")
        names = [r["name"] for r in result]
        # Beta Capital co-invested in AI Startup
        assert "Beta Capital" in names
        # Gamma Ventures co-invested in ML Corp
        assert "Gamma Ventures" in names

    def test_co_investor_count(self):
        kg = _make_test_graph()
        result = co_investors(kg, "Alpha VC")
        beta = next(r for r in result if r["name"] == "Beta Capital")
        assert beta["count"] == 1
        assert "AI Startup" in beta["shared_companies"]


class TestSearch:
    def test_search_by_name(self):
        kg = _make_test_graph()
        result = search(kg, "Alpha")
        assert len(result) >= 1
        assert any(r["name"] == "Alpha VC" for r in result)

    def test_search_case_insensitive(self):
        kg = _make_test_graph()
        result = search(kg, "alpha")
        assert len(result) >= 1

    def test_search_no_results(self):
        kg = _make_test_graph()
        result = search(kg, "zzzznotfound")
        assert result == []
