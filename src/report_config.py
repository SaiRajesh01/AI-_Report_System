"""
Report Configuration: Declarative specifications for multi-format regulatory reports
(PADER, PSUR/PBRER, DSUR, CSR).

Enables configuration-driven section routing, dependency graphs, and versioning.
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class SectionDefinition(BaseModel):
    """Declarative specification for a report section."""
    section_id: str
    title: str
    required_analyses: list[str] = Field(description="Domain analyses that supply evidence metrics to this section")
    generation_mode: Literal["deterministic", "llm", "hybrid"] = "llm"
    constraints: list[str] = Field(default_factory=list)
    system_prompt_override: str | None = None
    template_name: str | None = None
    dependencies: list[str] = Field(default_factory=list, description="Other sections that must be generated first")


class ReportSpecification(BaseModel):
    """Specification defining an entire regulatory report type."""
    report_type: str = Field(description="e.g. PADER, PSUR, DSUR, CSR")
    regulatory_framework: str = Field(description="e.g. FDA 21 CFR 314.80, ICH E2C(R2), ICH E2F, ICH E3")
    version: str = "1.0.0"
    sections: list[SectionDefinition]
    metadata_fields: list[str] = Field(default_factory=lambda: ["product_name", "application_number", "mah", "period"])

    def get_section(self, section_id: str) -> SectionDefinition | None:
        for s in self.sections:
            if s.section_id == section_id:
                return s
        return None

    def get_analysis_dependencies(self) -> set[str]:
        """Collect all required analysis domains across all sections."""
        deps = set()
        for s in self.sections:
            deps.update(s.required_analyses)
        return deps


# Standard PADER Specification
PADER_SPECIFICATION = ReportSpecification(
    report_type="PADER",
    regulatory_framework="United States FDA 21 CFR 314.80",
    version="1.0.0",
    sections=[
        SectionDefinition(
            section_id="reporting_period",
            title="1. Reporting Period",
            required_analyses=["case_analysis", "trend_analysis"],
            generation_mode="deterministic",
            constraints=["Fill exact metadata fields without prose elaboration."]
        ),
        SectionDefinition(
            section_id="narrative_summary",
            title="2. Narrative Summary and Analysis",
            required_analyses=["case_analysis", "demographic_analysis", "reaction_analysis", "outcome_analysis", "trend_analysis", "alert_analysis"],
            generation_mode="llm",
            constraints=[
                "Synthesize high-level clinical findings across volume, demographics, top reactions, seriousness, and drug role.",
                "Highlight concomitant medication role in complex multi-drug therapy.",
                "State factual reporting stability without declaring safety signals."
            ]
        ),
        SectionDefinition(
            section_id="case_summary",
            title="3. Summary Analysis of Cases",
            required_analyses=["case_analysis", "demographic_analysis", "alert_analysis"],
            generation_mode="llm",
            constraints=["Generate structured Markdown tables for volume, demographics, geography, qualification, and drug role."]
        ),
        SectionDefinition(
            section_id="reaction_analysis",
            title="4. Reaction / Adverse Event Analysis",
            required_analyses=["reaction_analysis", "outcome_analysis"],
            generation_mode="llm",
            constraints=[
                "Tabulate Top 20 Preferred Terms (PTs) with occurrences and distinct case counts.",
                "Explicitly state that System Organ Class (SOC) coding is UNAVAILABLE.",
                "Do NOT infer or invent SOC groupings."
            ]
        ),
        SectionDefinition(
            section_id="serious_cases",
            title="5. Serious Cases / 15-Day Alerts",
            required_analyses=["case_analysis", "alert_analysis", "reaction_analysis"],
            generation_mode="llm",
            constraints=[
                "Tabulate the 6 independent seriousness criteria.",
                "Explicitly state expectedness is OUT OF SCOPE due to lack of CCDS/label."
            ]
        ),
        SectionDefinition(
            section_id="trends",
            title="6. Trends and Important Observations",
            required_analyses=["trend_analysis", "reaction_analysis", "demographic_analysis", "case_analysis"],
            generation_mode="llm",
            constraints=["Summarize monthly and quarterly reporting volume without claiming safety signals."]
        ),
        SectionDefinition(
            section_id="history_of_actions",
            title="7. History of Actions",
            required_analyses=["alert_analysis"],
            generation_mode="deterministic",
            constraints=["State explicitly that no regulatory actions were reported."]
        ),
        SectionDefinition(
            section_id="case_listing",
            title="8. Case Index / Listing",
            required_analyses=["case_analysis", "trend_analysis"],
            generation_mode="deterministic",
            constraints=["Format a structured case index table for line-item traceability."]
        ),
    ]
)

# Registry of Regulatory Report Types
REPORT_SPECIFICATIONS: dict[str, ReportSpecification] = {
    "PADER": PADER_SPECIFICATION,
}
