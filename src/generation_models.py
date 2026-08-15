"""
Generation Models: Pydantic schemas for structured LLM section generation,
claim-level grounding, and validation tracking.
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class GroundedClaim(BaseModel):
    """An individual factual claim extracted from generated text and linked to evidence."""
    claim_text: str = Field(description="The exact sentence or statement in the generated section")
    evidence_id: str | None = Field(default=None, description="The evidence metric ID supporting this claim, e.g., 'CO-001'")
    extracted_figures: list[str] = Field(default_factory=list, description="Numbers or values mentioned in the claim")
    status: Literal["VERIFIED", "FLAGGED", "UNSUPPORTED"] = Field(
        default="VERIFIED",
        description="Verification status: VERIFIED = grounded in evidence, FLAGGED = ungrounded or out-of-scope claim"
    )
    flag_reason: str | None = Field(default=None, description="Reason if flagged or unsupported")


class SectionEvidencePacket(BaseModel):
    """Scoped evidence provided exclusively to a specific report section."""
    section_id: str
    section_title: str
    product_name: str
    reporting_period: dict[str, Any]
    approved_metrics: dict[str, Any] = Field(description="Key-value mapping of metric names to approved values")
    metric_catalog: list[dict[str, Any]] = Field(description="List of EvidenceMetric metadata including evidence_id and definition")
    constraints: list[str] = Field(description="Section-specific constraints and out-of-scope reminders")
    raw_sample_data: list[dict[str, Any]] | None = Field(default=None, description="Optional case listing sample for table generation")


class GeneratedSectionOutput(BaseModel):
    """Structured response expected from the LLM or deterministic fallback for each section."""
    section_name: str = Field(description="Section identifier or title")
    generated_text: str = Field(description="Markdown formatted prose and/or tables for the section")
    claims: list[GroundedClaim] = Field(default_factory=list, description="List of factual claims made in the text")
    evidence_ids_used: list[str] = Field(default_factory=list, description="List of evidence_ids referenced")
    warnings_or_uncertainties: list[str] = Field(default_factory=list, description="Explicit caveats, data gaps, or uncertainties")
    grounding_score: float = Field(default=1.0, description="Proportion of verified claims (0.0 to 1.0)")
    generation_mode: Literal["llm", "deterministic", "offline_fallback"] = Field(default="llm")


class CompleteDraftReport(BaseModel):
    """Master draft report assembling all generated sections and validation findings."""
    product_name: str
    application_number: str
    reporting_period: dict[str, Any]
    sections: dict[str, GeneratedSectionOutput]
    overall_grounding_score: float
    total_claims_count: int
    flagged_claims_count: int
    generated_markdown: str
