"""
Alert Analysis & Regulatory Metadata Module: 15-day expedited Alert analysis,
explicit History of Actions absence declaration, and Expectedness scoping.
"""
from __future__ import annotations

import pandas as pd
from src.evidence_model import EvidenceMetric, AnalysisSectionResult


def analyze_alerts(dedup_df: pd.DataFrame) -> AnalysisSectionResult:
    """
    Perform deterministic 15-day expedited Alert analysis and regulatory compliance scoping.

    Returns:
        AnalysisSectionResult containing structured EvidenceMetrics.
    """
    total_cases = len(dedup_df)
    metrics: list[EvidenceMetric] = []

    # 1. 15-Day Expedited / Alert Population
    expedited_series = dedup_df["fulfillexpeditecriteria"].fillna("no").astype(str).str.lower().str.strip()
    expedited_yes = int((expedited_series == "yes").sum())
    expedited_no = int((expedited_series == "no").sum())
    expedited_pct = round(expedited_yes / total_cases * 100, 2) if total_cases > 0 else 0.0

    metrics.append(EvidenceMetric(
        evidence_id="ALERT-001",
        metric_name="expedited_15day_alert_cases_count",
        value=expedited_yes,
        unit="cases",
        source_fields=["fulfillexpeditecriteria"],
        calculation_definition="COUNT(cases WHERE fulfillexpeditecriteria == 'yes')",
        scope="case-level"
    ))

    metrics.append(EvidenceMetric(
        evidence_id="ALERT-002",
        metric_name="expedited_15day_alert_cases_percentage",
        value=expedited_pct,
        unit="%",
        source_fields=["fulfillexpeditecriteria"],
        calculation_definition="(expedited_15day_alert_cases_count / total_unique_cases) * 100",
        scope="case-level"
    ))

    # 2. Cross-tabulation: Expedited vs Serious
    serious_series = dedup_df["serious"].fillna("not serious").astype(str).str.lower().str.strip()
    crosstab_serious = pd.crosstab(expedited_series, serious_series).to_dict()
    crosstab_formatted = {
        str(ser_val): {str(exp_val): int(count) for exp_val, count in inner_dict.items()}
        for ser_val, inner_dict in crosstab_serious.items()
    }

    metrics.append(EvidenceMetric(
        evidence_id="ALERT-SERIOUS-CROSSTAB",
        metric_name="expedited_vs_serious_crosstab",
        value=crosstab_formatted,
        unit="cases",
        source_fields=["fulfillexpeditecriteria", "serious"],
        calculation_definition="Cross-tabulation of fulfillexpeditecriteria by serious classification",
        scope="case-level",
        notes="Evaluates mathematical independence of seriousness and expedited flags."
    ))

    # 3. Expedited Cases by Fatal vs Non-Fatal
    expedited_df = dedup_df[expedited_series == "yes"]
    expedited_fatal = int((expedited_df["seriousnessdeath"] == "yes").sum())
    expedited_nonfatal = len(expedited_df) - expedited_fatal

    metrics.append(EvidenceMetric(
        evidence_id="ALERT-FATAL-SPLIT",
        metric_name="expedited_cases_fatal_split",
        value={
            "fatal_expedited_cases": expedited_fatal,
            "non_fatal_expedited_cases": expedited_nonfatal,
            "total_expedited_cases": len(expedited_df)
        },
        unit="cases",
        source_fields=["fulfillexpeditecriteria", "seriousnessdeath"],
        calculation_definition="COUNT(cases WHERE fulfillexpeditecriteria == 'yes') broken down by seriousnessdeath == 'yes'",
        scope="case-level"
    ))

    # 4. Expedited Cases by Report Type (Spontaneous vs Study)
    expedited_rt = expedited_df["reporttype"].value_counts().to_dict()
    metrics.append(EvidenceMetric(
        evidence_id="ALERT-REPORT-TYPE",
        metric_name="expedited_cases_report_type_breakdown",
        value={str(k): int(v) for k, v in expedited_rt.items()},
        unit="cases",
        source_fields=["fulfillexpeditecriteria", "reporttype"],
        calculation_definition="GROUP BY reporttype WHERE fulfillexpeditecriteria == 'yes'",
        scope="case-level"
    ))

    # 5. History of Actions Confirmation
    metrics.append(EvidenceMetric(
        evidence_id="HIST-ACTION-001",
        metric_name="history_of_actions_status",
        value={
            "actions_reported_in_dataset": False,
            "action_count": 0,
            "formal_statement": "No safety-related regulatory actions, labeling modifications, or risk-minimization interventions were reported during the interval covered by this report. No history-of-actions records were supplied in the dataset."
        },
        unit=None,
        source_fields=["safetyreportid"],
        calculation_definition="Regulatory compliance verification: Explicit confirmation of absence of reported actions",
        scope="dataset-level",
        notes="Strict grounding rule: Do not invent safety or regulatory actions."
    ))

    # 6. Expectedness Assessment Scoping
    metrics.append(EvidenceMetric(
        evidence_id="EXPECT-SCOPE-001",
        metric_name="expectedness_assessment_status",
        value={
            "expectedness_calculated": False,
            "reason": "No approved Company Core Data Sheet (CCDS) or Reference Safety Information (RSI) label was provided with the dataset for Version 0."
        },
        unit=None,
        source_fields=["patient_reaction_reactionmeddrapt"],
        calculation_definition="Compliance check: Expectedness analysis omitted due to lack of reference label",
        scope="dataset-level"
    ))

    return AnalysisSectionResult(
        section_id="alert_and_regulatory_analysis",
        section_title="15-Day Expedited Alerts and Regulatory Declarations",
        metrics=metrics,
        metadata={"total_expedited_cases": expedited_yes}
    )
