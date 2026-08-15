"""
Outcome Analysis Module: Reaction-level and case-level outcome distribution
using actual dataset categories and clinical worst-outcome hierarchy.
"""
from __future__ import annotations

import pandas as pd
from src.evidence_model import EvidenceMetric, AnalysisSectionResult
from src.reaction_analysis import unpack_reaction_rows

# Clinical severity ranking: higher index = more severe
OUTCOME_SEVERITY_ORDER = [
    "unknown",
    "recovered/resolved",
    "recovered/resolved with sequelae",
    "recovering/resolving",
    "not recovered/not resolved/ongoing",
    "fatal",
]


def determine_worst_case_outcome(rxn_df: pd.DataFrame) -> pd.Series:
    """
    Determine the single worst outcome for each case across all its reported reactions.
    """
    severity_map = {outcome: idx for idx, outcome in enumerate(OUTCOME_SEVERITY_ORDER)}

    def get_worst(series: pd.Series) -> str:
        max_severity = -1
        worst_str = "unknown"
        for val in series:
            norm_val = str(val).strip().lower()
            sev = severity_map.get(norm_val, 0)
            if sev > max_severity:
                max_severity = sev
                worst_str = norm_val
        return worst_str

    return rxn_df.groupby("safetyreportid")["outcome"].apply(get_worst)


def analyze_outcomes(dedup_df: pd.DataFrame) -> AnalysisSectionResult:
    """
    Perform deterministic outcome analysis at reaction-level and case-level.

    Returns:
        AnalysisSectionResult containing structured EvidenceMetrics.
    """
    rxn_df = unpack_reaction_rows(dedup_df)
    total_reactions = len(rxn_df)
    total_cases = len(dedup_df)

    metrics: list[EvidenceMetric] = []

    # 1. Reaction-Level Outcome Distribution
    rxn_outcome_counts = rxn_df["outcome"].value_counts().to_dict()
    rxn_outcome_summary = {}
    for outcome_name, count in rxn_outcome_counts.items():
        pct = round(int(count) / total_reactions * 100, 2) if total_reactions > 0 else 0.0
        rxn_outcome_summary[outcome_name] = {"count": int(count), "percentage": pct}

    metrics.append(EvidenceMetric(
        evidence_id="OUT-RXN-ALL",
        metric_name="reaction_level_outcome_distribution",
        value=rxn_outcome_summary,
        unit="reactions",
        source_fields=["patient_reaction_reactionoutcome"],
        calculation_definition="COUNT(reactions) GROUP BY outcome",
        scope="reaction-level"
    ))

    # 2. Case-Level Worst Outcome Distribution
    case_worst = determine_worst_case_outcome(rxn_df)
    case_outcome_counts = case_worst.value_counts().to_dict()
    case_outcome_summary = {}
    for outcome_name, count in case_outcome_counts.items():
        pct = round(int(count) / total_cases * 100, 2) if total_cases > 0 else 0.0
        case_outcome_summary[outcome_name] = {"count": int(count), "percentage": pct}

    metrics.append(EvidenceMetric(
        evidence_id="OUT-CASE-ALL",
        metric_name="case_level_worst_outcome_distribution",
        value=case_outcome_summary,
        unit="cases",
        source_fields=["patient_reaction_reactionoutcome"],
        calculation_definition="Worst reaction outcome per case based on clinical severity hierarchy (Fatal > Not recovered > Recovering > Recovered > Unknown)",
        scope="case-level"
    ))

    # 3. Outcome Distribution for Top 5 PTs Cross-Tabulation
    top_5_pts = rxn_df["pt"].value_counts().head(5).index.tolist()
    crosstab_dict = {}
    for pt in top_5_pts:
        subset = rxn_df[rxn_df["pt"] == pt]
        dist = subset["outcome"].value_counts().to_dict()
        crosstab_dict[pt] = {str(k): int(v) for k, v in dist.items()}

    metrics.append(EvidenceMetric(
        evidence_id="OUT-CROSSTAB-TOP5",
        metric_name="top_5_pts_outcome_crosstab",
        value=crosstab_dict,
        unit="reactions",
        source_fields=["patient_reaction_reactionmeddrapt", "patient_reaction_reactionoutcome"],
        calculation_definition="Crosstabulation of reaction outcomes for top 5 Preferred Terms",
        scope="reaction-level"
    ))

    return AnalysisSectionResult(
        section_id="outcome_analysis",
        section_title="Reaction and Case-Level Outcome Analysis",
        metrics=metrics,
        metadata={
            "outcome_categories_detected": list(rxn_outcome_counts.keys()),
            "severity_hierarchy": OUTCOME_SEVERITY_ORDER
        }
    )
