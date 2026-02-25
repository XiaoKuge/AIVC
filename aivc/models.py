"""Pydantic models for the AI VC Knowledge Graph."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Event(BaseModel):
    """A recorded event on a node or edge (provenance / audit trail)."""

    type: str        # "created" | "updated" | "invested" | "partnered" | "personal_inv"
    date: str        # UTC ISO timestamp of when the event was recorded
    description: str  # Human-readable summary
    source_url: str = ""  # Source URL if available


class VCFirm(BaseModel):
    """A venture capital firm."""

    name: str
    type: str = "VC"
    hq_region: str = ""
    hq_city: str = ""
    stage_focus: str = ""
    check_size: str = ""
    ai_focus: str = ""
    aum: str = ""
    website: str = ""
    last_updated: str = ""
    source: str = ""


class Company(BaseModel):
    """A company that received investment."""

    name: str
    sector: str = ""
    website: str = ""
    founded_year: Optional[int] = None
    last_updated: str = ""
    source: str = ""


class Person(BaseModel):
    """An individual investor or partner."""

    name: str
    title: str = ""
    linkedin: str = ""
    notes: str = ""
    last_updated: str = ""
    source: str = ""


class Deal(BaseModel):
    """An investment deal (edge data for invested_in)."""

    amount: str = ""
    round: str = ""
    date: str = ""
    source: str = ""
    last_updated: str = ""


class PartnerEdge(BaseModel):
    """Edge data for partner_at relationship."""

    title: str = ""
    source: str = ""
    last_updated: str = ""


class PersonalInvestmentEdge(BaseModel):
    """Edge data for personal_investment relationship."""

    notes: str = ""
    source: str = ""
    last_updated: str = ""


def node_id(name: str) -> str:
    """Generate a stable node ID from an entity name.

    Lowercases, strips whitespace, replaces spaces with hyphens,
    and removes common suffixes/noise.
    """
    nid = name.strip().lower()
    nid = nid.replace(" ", "-")
    # Remove parenthetical suffixes for ID but keep in display name
    # e.g., "Andreessen Horowitz (a16z)" -> "andreessen-horowitz-(a16z)"
    return nid
