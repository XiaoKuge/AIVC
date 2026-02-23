"""Tests for the knowledge graph wrapper."""

import json
import tempfile
from pathlib import Path

import pytest

from aivc.graph import COMPANY, FIRM, INVESTED_IN, PARTNER_AT, PERSON, KnowledgeGraph
from aivc.models import Company, Deal, PartnerEdge, Person, VCFirm


class TestKnowledgeGraph:
    def test_add_firm(self):
        kg = KnowledgeGraph()
        nid = kg.add_firm(VCFirm(name="Test VC", type="VC", hq_region="NA"))
        assert nid == "test-vc"
        assert kg.g.nodes[nid]["name"] == "Test VC"
        assert kg.g.nodes[nid]["node_type"] == FIRM

    def test_add_company(self):
        kg = KnowledgeGraph()
        nid = kg.add_company(Company(name="Acme Corp"))
        assert nid == "acme-corp"
        assert kg.g.nodes[nid]["node_type"] == COMPANY

    def test_add_person(self):
        kg = KnowledgeGraph()
        nid = kg.add_person(Person(name="Jane Doe", title="GP"))
        assert nid == "jane-doe"
        assert kg.g.nodes[nid]["node_type"] == PERSON

    def test_add_investment(self):
        kg = KnowledgeGraph()
        kg.add_firm(VCFirm(name="Test VC"))
        kg.add_company(Company(name="Startup Inc"))
        kg.add_investment("Test VC", "Startup Inc", Deal(amount="$10M", round="Series A"))

        edges = kg.edges_by_type(INVESTED_IN)
        assert len(edges) == 1
        assert edges[0][0] == "test-vc"
        assert edges[0][1] == "startup-inc"
        assert edges[0][2]["amount"] == "$10M"

    def test_add_partner(self):
        kg = KnowledgeGraph()
        kg.add_person(Person(name="Bob Smith"))
        kg.add_firm(VCFirm(name="Big VC"))
        kg.add_partner("Bob Smith", "Big VC", PartnerEdge(title="Managing Partner"))

        edges = kg.edges_by_type(PARTNER_AT)
        assert len(edges) == 1
        assert edges[0][2]["title"] == "Managing Partner"

    def test_merge_node_idempotent(self):
        """Re-adding a node should update it, not duplicate it."""
        kg = KnowledgeGraph()
        kg.add_firm(VCFirm(name="Test VC", hq_region="NA"))
        kg.add_firm(VCFirm(name="Test VC", hq_region="EU"))

        firms = kg.firms()
        assert len(firms) == 1
        assert firms[0][1]["hq_region"] == "EU"

    def test_merge_preserves_nonempty(self):
        """Merging should not overwrite non-empty fields with empty ones."""
        kg = KnowledgeGraph()
        kg.add_firm(VCFirm(name="Test VC", hq_region="NA", aum="$1B"))
        kg.add_firm(VCFirm(name="Test VC", hq_region="EU"))  # aum is empty

        firms = kg.firms()
        assert firms[0][1]["hq_region"] == "EU"
        assert firms[0][1]["aum"] == "$1B"  # Preserved

    def test_save_and_load(self):
        kg = KnowledgeGraph()
        kg.add_firm(VCFirm(name="Test VC"))
        kg.add_company(Company(name="Acme"))
        kg.add_investment("Test VC", "Acme", Deal(amount="$5M"))

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        kg.save(path)
        kg2 = KnowledgeGraph.load(path)

        assert kg2.stats()["firms"] == 1
        assert kg2.stats()["companies"] == 1
        assert kg2.stats()["investments"] == 1

        Path(path).unlink()

    def test_stats(self):
        kg = KnowledgeGraph()
        kg.add_firm(VCFirm(name="VC1"))
        kg.add_firm(VCFirm(name="VC2"))
        kg.add_company(Company(name="Co1"))
        kg.add_person(Person(name="P1"))
        kg.add_investment("VC1", "Co1")
        kg.add_investment("VC2", "Co1")

        stats = kg.stats()
        assert stats["firms"] == 2
        assert stats["companies"] == 1
        assert stats["people"] == 1
        assert stats["investments"] == 2

    def test_auto_create_stub_nodes(self):
        """Investment edges should auto-create stub nodes if needed."""
        kg = KnowledgeGraph()
        kg.add_investment("New VC", "New Startup")

        assert "new-vc" in kg.g
        assert "new-startup" in kg.g
        assert kg.g.nodes["new-vc"]["node_type"] == FIRM
        assert kg.g.nodes["new-startup"]["node_type"] == COMPANY
