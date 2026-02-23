"""NetworkX DiGraph wrapper for the AI VC Knowledge Graph."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import networkx as nx

from aivc.models import (
    Company,
    Deal,
    PartnerEdge,
    Person,
    PersonalInvestmentEdge,
    VCFirm,
    node_id,
)

# Node type constants
FIRM = "VCFirm"
COMPANY = "Company"
PERSON = "Person"

# Edge type constants
INVESTED_IN = "invested_in"
PARTNER_AT = "partner_at"
PERSONAL_INVESTMENT = "personal_investment"


class KnowledgeGraph:
    """Wrapper around NetworkX DiGraph for AI VC data.

    Provides idempotent merge operations so re-running scrapers
    won't create duplicates.
    """

    def __init__(self) -> None:
        self.g = nx.DiGraph()

    # ── Node operations ─────────────────────────────────────────

    def add_firm(self, firm: VCFirm) -> str:
        """Add or update a VC firm node. Returns node ID."""
        nid = node_id(firm.name)
        self._merge_node(nid, FIRM, firm.model_dump())
        return nid

    def add_company(self, company: Company) -> str:
        """Add or update a company node. Returns node ID."""
        nid = node_id(company.name)
        self._merge_node(nid, COMPANY, company.model_dump())
        return nid

    def add_person(self, person: Person) -> str:
        """Add or update a person node. Returns node ID."""
        nid = node_id(person.name)
        self._merge_node(nid, PERSON, person.model_dump())
        return nid

    def _merge_node(self, nid: str, node_type: str, attrs: dict[str, Any]) -> None:
        """Idempotent merge: create or update a node."""
        if not attrs.get("last_updated"):
            attrs["last_updated"] = _now()
        attrs["node_type"] = node_type
        if nid in self.g:
            # Merge: update non-empty fields only
            existing = self.g.nodes[nid]
            for k, v in attrs.items():
                if v not in (None, "", 0):
                    existing[k] = v
        else:
            self.g.add_node(nid, **attrs)

    # ── Edge operations ─────────────────────────────────────────

    def add_investment(self, firm_name: str, company_name: str, deal: Deal | None = None) -> None:
        """Add invested_in edge from firm to company."""
        firm_id = node_id(firm_name)
        company_id = node_id(company_name)
        # Ensure nodes exist (minimal stubs if not already present)
        if firm_id not in self.g:
            self.add_firm(VCFirm(name=firm_name))
        if company_id not in self.g:
            self.add_company(Company(name=company_name))
        attrs = (deal or Deal()).model_dump()
        self._merge_edge(firm_id, company_id, INVESTED_IN, attrs)

    def add_partner(self, person_name: str, firm_name: str, edge: PartnerEdge | None = None) -> None:
        """Add partner_at edge from person to firm."""
        person_id = node_id(person_name)
        firm_id = node_id(firm_name)
        if person_id not in self.g:
            self.add_person(Person(name=person_name))
        if firm_id not in self.g:
            self.add_firm(VCFirm(name=firm_name))
        attrs = (edge or PartnerEdge()).model_dump()
        self._merge_edge(person_id, firm_id, PARTNER_AT, attrs)

    def add_personal_investment(
        self, person_name: str, company_name: str, edge: PersonalInvestmentEdge | None = None
    ) -> None:
        """Add personal_investment edge from person to company."""
        person_id = node_id(person_name)
        company_id = node_id(company_name)
        if person_id not in self.g:
            self.add_person(Person(name=person_name))
        if company_id not in self.g:
            self.add_company(Company(name=company_name))
        attrs = (edge or PersonalInvestmentEdge()).model_dump()
        self._merge_edge(person_id, company_id, PERSONAL_INVESTMENT, attrs)

    def _merge_edge(self, src: str, dst: str, edge_type: str, attrs: dict[str, Any]) -> None:
        """Idempotent merge: create or update an edge."""
        if not attrs.get("last_updated"):
            attrs["last_updated"] = _now()
        attrs["edge_type"] = edge_type
        if self.g.has_edge(src, dst):
            existing = self.g.edges[src, dst]
            # Only update if same edge type
            if existing.get("edge_type") == edge_type:
                for k, v in attrs.items():
                    if v not in (None, "", 0):
                        existing[k] = v
            # Different edge type: use multi-edge key approach via attribute
        else:
            self.g.add_edge(src, dst, **attrs)

    # ── Persistence ─────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        """Save graph to JSON (pretty-printed, sorted keys for git diffs)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(self.g)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)

    @classmethod
    def load(cls, path: str | Path) -> "KnowledgeGraph":
        """Load graph from JSON."""
        path = Path(path)
        with open(path) as f:
            data = json.load(f)
        kg = cls()
        kg.g = nx.node_link_graph(data)
        return kg

    # ── Accessors ───────────────────────────────────────────────

    def nodes_by_type(self, node_type: str) -> list[tuple[str, dict]]:
        """Return all nodes of a given type."""
        return [
            (nid, attrs)
            for nid, attrs in self.g.nodes(data=True)
            if attrs.get("node_type") == node_type
        ]

    def firms(self) -> list[tuple[str, dict]]:
        return self.nodes_by_type(FIRM)

    def companies(self) -> list[tuple[str, dict]]:
        return self.nodes_by_type(COMPANY)

    def people(self) -> list[tuple[str, dict]]:
        return self.nodes_by_type(PERSON)

    def edges_by_type(self, edge_type: str) -> list[tuple[str, str, dict]]:
        """Return all edges of a given type."""
        return [
            (u, v, d)
            for u, v, d in self.g.edges(data=True)
            if d.get("edge_type") == edge_type
        ]

    def stats(self) -> dict[str, int]:
        """Return summary statistics."""
        return {
            "firms": len(self.firms()),
            "companies": len(self.companies()),
            "people": len(self.people()),
            "investments": len(self.edges_by_type(INVESTED_IN)),
            "partnerships": len(self.edges_by_type(PARTNER_AT)),
            "personal_investments": len(self.edges_by_type(PERSONAL_INVESTMENT)),
            "total_nodes": self.g.number_of_nodes(),
            "total_edges": self.g.number_of_edges(),
        }


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
