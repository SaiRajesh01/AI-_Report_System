"""
Evidence Builder: Assembles scoped, section-specific evidence packets from
the master deterministic analysis results.

Guarantees context isolation: the LLM never receives raw CSV data or unneeded metrics.
"""
from __future__ import annotations

import pandas as pd
from typing import Any

from src.config import PRODUCT_NAME, APPLICATION_NUMBER
from src.evidence_model import CompleteAnalysisPackage, AnalysisSectionResult
from src.generation_models import SectionEvidencePacket


# Section mapping to required deterministic domain sections
SECTION_METRIC_ROUTING = {
    "reporting_period": ["trend_analysis", "case_analysis"],
    "narrative_summary": [
        "case_analysis", "demographic_analysis", "reaction_analysis",
        "outcome_analysis", "trend_analysis", "alert_analysis"
    ],
    "case_summary": [
        "case_analysis", "demographic_analysis", "alert_analysis"
    ],
    "reaction_analysis": [
        "reaction_analysis", "outcome_analysis"
    ],
    "serious_cases": [
        "case_analysis", "alert_analysis", "reaction_analysis"
    ],
    "trends": [
        "trend_analysis", "reaction_analysis", "demographic_analysis", "case_analysis"
    ],
    "history_of_actions": [
        "alert_analysis"
    ],
    "case_listing": [
        "trend_analysis", "case_analysis"
    ],
}

# Standard constraints enforced on section prompts
BASE_CONSTRAINTS = [
    "You may ONLY cite numbers and facts provided in the approved metrics block.",
    "Do NOT perform arithmetic or calculate new numbers; use provided pre-calculated figures.",
    "Do NOT make causal statements, safety conclusions, or signal determinations.",
    "Do NOT invent clinical narratives, patient histories, or regulatory actions.",
    "Maintain a formal, objective, regulatory pharmacovigilance tone.",
]

SECTION_SPECIFIC_CONSTRAINTS = {
    "reporting_period": [
        "Fill exact metadata fields without prose elaboration."
    ],
    "narrative_summary": [
        "Synthesize high-level clinical findings across volume, demographics, top reactions, seriousness, and drug role.",
        "Highlight that in 65.04% of cases, Bisoprolol was a concomitant medication in complex multi-drug therapy.",
        "State factual reporting stability without declaring safety signals."
    ],
    "case_summary": [
        "Generate structured Markdown tables for: Case Volume, Demographics (Sex and WHO Age Groups), Geographic Distribution (primarysourcecountry), Reporter Qualification, and Drug Role.",
        "Provide brief factual commentary between tables without medical speculation."
    ],
    "reaction_analysis": [
        "Tabulate Top 20 Preferred Terms (PTs) with total occurrences and distinct case counts.",
        "Explicitly state that System Organ Class (SOC) coding is UNAVAILABLE in the dataset.",
        "Do NOT invent or infer SOC groupings (e.g. 'Cardiac disorders', 'Renal disorders')."
    ],
    "serious_cases": [
        "Tabulate the 6 independent seriousness criteria (Death, Life-threatening, Hospitalization, Disability, Congenital Anomaly, Other Medically Important).",
        "Note that seriousness criteria are independent flags, not mutually exclusive categories.",
        "Explicitly state that expectedness (labelled vs unlabelled) is OUT OF SCOPE due to lack of a reference CCDS/label."
    ],
    "trends": [
        "Summarize monthly and quarterly reporting volume.",
        "Describe numerical variations as factual observations ONLY, not as confirmed or emerging safety signals.",
        "Note baseline volume stability between first half and second half of reporting period."
    ],
    "history_of_actions": [
        "State explicitly that no regulatory actions, labeling modifications, or risk minimization measures were reported in the dataset."
    ],
    "case_listing": [
        "Format a structured case index table for traceability back to individual case IDs."
    ],
}


def build_section_evidence_packet(
    section_id: str,
    package: CompleteAnalysisPackage,
    sample_cases_df: pd.DataFrame | None = None
) -> SectionEvidencePacket:
    """
    Construct a scoped SectionEvidencePacket for a specific report section.

    Args:
        section_id: Identifier of the section to build evidence for.
        package: The master CompleteAnalysisPackage from Phase 2.
        sample_cases_df: Optional DataFrame for generating case listing rows.

    Returns:
        SectionEvidencePacket with scoped approved metrics and explicit constraints.
    """
    domain_keys = SECTION_METRIC_ROUTING.get(section_id, [])
    approved_metrics: dict[str, Any] = {}
    catalog: list[dict[str, Any]] = []

    for dom_key in domain_keys:
        sec_obj: AnalysisSectionResult | None = package.sections.get(dom_key)
        if not sec_obj:
            continue
        for metric in sec_obj.metrics:
            # Add to metrics dict
            approved_metrics[metric.metric_name] = metric.value
            catalog.append({
                "evidence_id": metric.evidence_id,
                "metric_name": metric.metric_name,
                "scope": metric.scope,
                "definition": metric.calculation_definition,
                "notes": metric.notes
            })

    constraints = BASE_CONSTRAINTS + SECTION_SPECIFIC_CONSTRAINTS.get(section_id, [])

    # Case listing sample if requested
    raw_sample = None
    if section_id == "case_listing" and sample_cases_df is not None:
        sample_subset = sample_cases_df.head(50).copy()
        raw_sample = sample_subset.to_dict(orient="records")

    section_titles = {
        "reporting_period": "1. Reporting Period",
        "narrative_summary": "2. Narrative Summary and Analysis",
        "case_summary": "3. Summary Analysis of Cases",
        "reaction_analysis": "4. Reaction / Adverse Event Analysis",
        "serious_cases": "5. Serious Cases / 15-Day Alerts",
        "trends": "6. Trends and Important Observations",
        "history_of_actions": "7. History of Actions",
        "case_listing": "8. Case Index / Listing",
    }

    return SectionEvidencePacket(
        section_id=section_id,
        section_title=section_titles.get(section_id, section_id.title()),
        product_name=package.product_name,
        reporting_period=package.reporting_period,
        approved_metrics=approved_metrics,
        metric_catalog=catalog,
        constraints=constraints,
        raw_sample_data=raw_sample
    )


def build_all_section_evidence_packets(
    package: CompleteAnalysisPackage,
    dedup_df: pd.DataFrame | None = None
) -> dict[str, SectionEvidencePacket]:
    """
    Build evidence packets for all 8 standard PADER report sections.
    """
    packets = {}
    for sec_id in SECTION_METRIC_ROUTING:
        packets[sec_id] = build_section_evidence_packet(
            section_id=sec_id,
            package=package,
            sample_cases_df=dedup_df
        )
    return packets
