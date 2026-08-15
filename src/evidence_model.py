"""
Evidence Model: Pydantic schemas for deterministic safety analysis metrics.

Every metric in the pharmacovigilance analysis is wrapped in an EvidenceMetric
with an immutable evidence_id, metric name, exact value, unit, source field(s),
calculation definition, analysis scope, and optional supporting case IDs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field


class EvidenceMetric(BaseModel):
    """A single atomic, auditable evidence metric calculated by deterministic Python code."""
    evidence_id: str = Field(description="Unique metric identifier, e.g., 'CO-001', 'DEMO-002'")
    metric_name: str = Field(description="Human-readable name of the metric")
    value: Any = Field(description="Deterministic calculation result (number, string, dict, or list)")
    unit: str | None = Field(default=None, description="Unit of measurement if applicable, e.g., 'cases', '%', 'years'")
    source_fields: list[str] = Field(description="Columns/fields from the raw dataset used in this calculation")
    calculation_definition: str = Field(description="Formal definition of the mathematical or logical calculation")
    scope: Literal["case-level", "reaction-level", "dataset-level"] = Field(
        description="Whether calculation is at case-level, reaction-level, or overall dataset"
    )
    supporting_case_ids: list[int | str] | None = Field(
        default=None,
        description="Sample or complete list of case identifiers contributing to this metric"
    )
    notes: str | None = Field(default=None, description="Regulatory or methodological notes")


class AnalysisSectionResult(BaseModel):
    """A collection of related evidence metrics belonging to a specific analytical domain."""
    section_id: str
    section_title: str
    metrics: list[EvidenceMetric]
    metadata: dict[str, Any] = Field(default_factory=dict)
    computed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def get_metric(self, evidence_id: str) -> EvidenceMetric | None:
        """Lookup an evidence metric by its ID."""
        for m in self.metrics:
            if m.evidence_id == evidence_id:
                return m
        return None

    def to_figures_dict(self) -> dict[str, Any]:
        """Convert metrics to a key-value dictionary for LLM context packing."""
        return {m.metric_name: m.value for m in self.metrics}


class ValidationSummary(BaseModel):
    """Complete summary of dataset validation and structural health checks."""
    dataset_file: str
    total_raw_rows: int
    unique_cases: int
    duplicate_rows_count: int
    columns_count: int
    required_columns_checked: list[str]
    missing_required_columns: list[str]
    date_range_start: str
    date_range_end: str
    missing_value_summary: dict[str, dict[str, Any]]
    column_dtypes: dict[str, str]
    structural_discrepancies: list[str]
    validation_status: Literal["PASS", "FAIL", "WARNING"]
    validated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CompleteAnalysisPackage(BaseModel):
    """Root container packaging all deterministic analysis sections and validation."""
    product_name: str
    reporting_period: dict[str, Any]
    validation_summary: ValidationSummary
    sections: dict[str, AnalysisSectionResult]
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
