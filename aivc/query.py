"""Query functions for the AI VC Knowledge Graph."""

from __future__ import annotations

from aivc.graph import INVESTED_IN, PARTNER_AT, KnowledgeGraph
from aivc.models import node_id


def portfolio(kg: KnowledgeGraph, firm_name: str) -> list[dict]:
    """Get all companies a firm has invested in."""
    fid = node_id(firm_name)
    results = []
    for _, target, data in kg.g.out_edges(fid, data=True):
        if data.get("edge_type") == INVESTED_IN:
            company_data = kg.g.nodes.get(target, {})
            results.append({
                "id": target,
                "name": company_data.get("name", target),
                **{k: v for k, v in data.items() if k != "edge_type"},
            })
    return sorted(results, key=lambda x: x["name"])


def investors(kg: KnowledgeGraph, company_name: str) -> list[dict]:
    """Get all firms that invested in a company."""
    cid = node_id(company_name)
    results = []
    for src, _, data in kg.g.in_edges(cid, data=True):
        if data.get("edge_type") == INVESTED_IN:
            firm_data = kg.g.nodes.get(src, {})
            results.append({
                "id": src,
                "name": firm_data.get("name", src),
                "type": firm_data.get("type", ""),
            })
    return sorted(results, key=lambda x: x["name"])


def co_investors(kg: KnowledgeGraph, firm_name: str) -> list[dict]:
    """Find firms that co-invested with the given firm (share portfolio companies)."""
    fid = node_id(firm_name)
    # Get all companies this firm invested in
    my_companies = set()
    for _, target, data in kg.g.out_edges(fid, data=True):
        if data.get("edge_type") == INVESTED_IN:
            my_companies.add(target)

    # Find other firms that also invested in those companies
    co_investor_map: dict[str, set[str]] = {}
    for company_id in my_companies:
        for src, _, data in kg.g.in_edges(company_id, data=True):
            if data.get("edge_type") == INVESTED_IN and src != fid:
                if src not in co_investor_map:
                    co_investor_map[src] = set()
                co_investor_map[src].add(company_id)

    results = []
    for other_id, shared in co_investor_map.items():
        firm_data = kg.g.nodes.get(other_id, {})
        shared_names = [kg.g.nodes.get(c, {}).get("name", c) for c in shared]
        results.append({
            "id": other_id,
            "name": firm_data.get("name", other_id),
            "shared_companies": sorted(shared_names),
            "count": len(shared),
        })
    return sorted(results, key=lambda x: -x["count"])


def search(kg: KnowledgeGraph, term: str) -> list[dict]:
    """Search all nodes by name (case-insensitive substring match)."""
    term_lower = term.lower()
    results = []
    for nid, attrs in kg.g.nodes(data=True):
        name = attrs.get("name", nid)
        if term_lower in name.lower() or term_lower in nid:
            results.append({
                "id": nid,
                "name": name,
                "type": attrs.get("node_type", "unknown"),
            })
    return sorted(results, key=lambda x: x["name"])


def firm_details(kg: KnowledgeGraph, firm_name: str) -> dict | None:
    """Get full details for a firm including partners and portfolio."""
    fid = node_id(firm_name)
    if fid not in kg.g:
        return None
    attrs = dict(kg.g.nodes[fid])

    # Portfolio
    port = portfolio(kg, firm_name)

    # Partners
    partners = []
    for src, _, data in kg.g.in_edges(fid, data=True):
        if data.get("edge_type") == PARTNER_AT:
            person_data = kg.g.nodes.get(src, {})
            partners.append({
                "id": src,
                "name": person_data.get("name", src),
                "title": data.get("title", ""),
            })

    return {
        **attrs,
        "portfolio": port,
        "partners": sorted(partners, key=lambda x: x["name"]),
    }
