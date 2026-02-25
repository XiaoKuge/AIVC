"""NetworkX MultiDiGraph wrapper for the AI VC Knowledge Graph."""

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
    """Wrapper around NetworkX MultiDiGraph for AI VC data.

    Uses MultiDiGraph to support multiple investment rounds between
    the same firm→company pair (e.g. Series A, then Series B).

    Provides idempotent merge operations so re-running scrapers
    won't create duplicates.
    """

    def __init__(self) -> None:
        self.g = nx.MultiDiGraph()

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
        timestamp = attrs["last_updated"]
        source_url = _extract_source_url(attrs.get("source", ""))
        name = attrs.get("name", nid)

        if nid in self.g:
            # Merge: update non-empty fields only
            existing = self.g.nodes[nid]
            changed = []
            for k, v in attrs.items():
                if v not in (None, "", 0) and k not in ("events",):
                    if existing.get(k) != v and k not in ("last_updated", "node_type"):
                        changed.append(k)
                    existing[k] = v
            if changed:
                events = existing.setdefault("events", [])
                events.append({
                    "type": "updated",
                    "date": timestamp,
                    "description": f"Updated: {', '.join(changed)}",
                    "source_url": source_url,
                })
        else:
            attrs.setdefault("events", [])
            attrs["events"].append({
                "type": "created",
                "date": timestamp,
                "description": f"Discovered: {name}",
                "source_url": source_url,
            })
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
        """Idempotent merge: create or update an edge.

        Uses (edge_type, round, date) as the edge key so that multiple
        investment rounds between the same pair coexist.
        """
        if not attrs.get("last_updated"):
            attrs["last_updated"] = _now()
        attrs["edge_type"] = edge_type
        timestamp = attrs["last_updated"]
        source_url = _extract_source_url(attrs.get("source", ""))

        # Build a stable key to distinguish multiple investments
        round_val = attrs.get("round", "")
        date_val = attrs.get("date", "")
        if round_val or date_val:
            key = f"{edge_type}:{round_val}:{date_val}"
        else:
            key = edge_type

        # Build human-readable description for the event
        src_name = self.g.nodes[src].get("name", src) if src in self.g else src
        dst_name = self.g.nodes[dst].get("name", dst) if dst in self.g else dst

        if self.g.has_edge(src, dst, key=key):
            # Update existing edge with same key
            existing = self.g.edges[src, dst, key]
            changed = []
            for k, v in attrs.items():
                if v not in (None, "", 0) and k not in ("events",):
                    if existing.get(k) != v and k not in ("last_updated", "edge_type"):
                        changed.append(k)
                    existing[k] = v
            if changed:
                events = existing.setdefault("events", [])
                events.append({
                    "type": "updated",
                    "date": timestamp,
                    "description": f"Updated: {', '.join(changed)}",
                    "source_url": source_url,
                })
        else:
            # Check for a bare edge (no round/date) that should be upgraded
            if (round_val or date_val) and key != edge_type:
                for bare_key in [edge_type, 0]:
                    if self.g.has_edge(src, dst, key=bare_key):
                        ex = self.g.edges[src, dst, bare_key]
                        if ex.get("edge_type") == edge_type and not ex.get("round") and not ex.get("date"):
                            # Upgrade: remove bare edge, will be re-added with proper key
                            self.g.remove_edge(src, dst, key=bare_key)
                            break

            # Build event description
            desc_parts = [f"{src_name} → {dst_name}"]
            if round_val:
                desc_parts.append(round_val)
            if attrs.get("amount"):
                desc_parts.append(attrs["amount"])
            evt_type_map = {
                INVESTED_IN: "invested",
                PARTNER_AT: "partnered",
                PERSONAL_INVESTMENT: "personal_inv",
            }
            evt_type = evt_type_map.get(edge_type, "created")

            attrs.setdefault("events", [])
            attrs["events"].append({
                "type": evt_type,
                "date": timestamp,
                "description": " | ".join(desc_parts),
                "source_url": source_url,
            })
            self.g.add_edge(src, dst, key=key, **attrs)

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
        """Load graph from JSON.

        Handles backward compatibility: old DiGraph JSON (multigraph=false)
        is loaded as MultiDiGraph with existing edges getting key=0.
        """
        path = Path(path)
        with open(path) as f:
            data = json.load(f)
        kg = cls()
        # Ensure old DiGraph JSON loads as MultiDiGraph
        if not data.get("multigraph"):
            data["multigraph"] = True
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


def _extract_source_url(source: str) -> str:
    """Extract a URL from a source string, if present."""
    if not source:
        return ""
    if source.startswith("curated:"):
        url = source[len("curated:"):]
        return url if url.startswith("http") else ""
    if source.startswith("http"):
        return source
    return ""
