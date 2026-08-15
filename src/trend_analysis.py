"""
Trend Analysis Module: Reporting period derivation, monthly/quarterly case volumes,
volume velocity, and Preferred Term trajectories without unsupported safety signal claims.
"""
from __future__ import annotations

import pandas as pd
from src.evidence_model import EvidenceMetric, AnalysisSectionResult
from src.reaction_analysis import unpack_reaction_rows


def analyze_trends(dedup_df: pd.DataFrame) -> AnalysisSectionResult:
    """
    Perform deterministic time and volume trend analysis based on receivedate.

    Returns:
        AnalysisSectionResult containing structured EvidenceMetrics.
    """
    metrics: list[EvidenceMetric] = []
    df = dedup_df.copy()

    # 1. Parse Receive Dates and Determine Reporting Period
    if "parsed_receivedate" in df.columns:
        dates = df["parsed_receivedate"]
    else:
        dates = pd.to_datetime(df["receivedate"].astype(str), format="%Y%m%d", errors="coerce")

    df["_date"] = dates
    valid_dates = df["_date"].dropna()
    total_valid_cases = len(valid_dates)

    if total_valid_cases > 0:
        start_date = valid_dates.min().strftime("%Y-%m-%d")
        end_date = valid_dates.max().strftime("%Y-%m-%d")
        duration_days = int((valid_dates.max() - valid_dates.min()).days)
    else:
        start_date = "UNKNOWN"
        end_date = "UNKNOWN"
        duration_days = 0

    period_data = {
        "start_date": start_date,
        "end_date": end_date,
        "duration_days": duration_days,
        "total_cases_in_period": total_valid_cases
    }

    metrics.append(EvidenceMetric(
        evidence_id="TIME-PERIOD-001",
        metric_name="reporting_period_interval",
        value=period_data,
        unit="days",
        source_fields=["receivedate"],
        calculation_definition="MIN(parsed_receivedate) to MAX(parsed_receivedate)",
        scope="dataset-level"
    ))

    # 2. Monthly Case Counts
    df["_month"] = df["_date"].dt.to_period("M").astype(str)
    monthly_counts = df["_month"].value_counts().sort_index().to_dict()
    monthly_summary = {str(k): int(v) for k, v in monthly_counts.items() if k != "NaT"}

    metrics.append(EvidenceMetric(
        evidence_id="TIME-MONTHLY-COUNTS",
        metric_name="monthly_case_volume_distribution",
        value=monthly_summary,
        unit="cases",
        source_fields=["receivedate"],
        calculation_definition="GROUP BY Year-Month(receivedate) -> count",
        scope="case-level"
    ))

    # 3. Quarterly Case Counts
    df["_quarter"] = df["_date"].dt.to_period("Q").astype(str)
    quarterly_counts = df["_quarter"].value_counts().sort_index().to_dict()
    quarterly_summary = {str(k): int(v) for k, v in quarterly_counts.items() if k != "NaT"}

    metrics.append(EvidenceMetric(
        evidence_id="TIME-QUARTERLY-COUNTS",
        metric_name="quarterly_case_volume_distribution",
        value=quarterly_summary,
        unit="cases",
        source_fields=["receivedate"],
        calculation_definition="GROUP BY Year-Quarter(receivedate) -> count",
        scope="case-level"
    ))

    # 4. Volume Velocity / First Half vs Second Half Comparison
    if total_valid_cases > 0:
        mid_date = valid_dates.min() + (valid_dates.max() - valid_dates.min()) / 2
        first_half = int((valid_dates <= mid_date).sum())
        second_half = int((valid_dates > mid_date).sum())
        pct_change = round((second_half - first_half) / first_half * 100, 2) if first_half > 0 else 0.0

        if pct_change > 15.0:
            direction = "increasing"
        elif pct_change < -15.0:
            direction = "decreasing"
        else:
            direction = "stable"

        velocity_data = {
            "first_half_cases": first_half,
            "second_half_cases": second_half,
            "percentage_change": pct_change,
            "trend_direction": direction
        }

        metrics.append(EvidenceMetric(
            evidence_id="TIME-VELOCITY-001",
            metric_name="reporting_volume_velocity",
            value=velocity_data,
            unit="cases",
            source_fields=["receivedate"],
            calculation_definition="Comparison of case volume in first half vs second half of reporting interval",
            scope="dataset-level",
            notes="Evaluates baseline stability. Fluctuation within +/-15% is classified as stable."
        ))

    # 5. Top Preferred Term Monthly Trajectories
    rxn_df = unpack_reaction_rows(dedup_df)
    case_date_map = dict(zip(dedup_df["safetyreportid"], df["_month"]))
    rxn_df["_month"] = rxn_df["safetyreportid"].map(case_date_map)

    top_5_pts = rxn_df["pt"].value_counts().head(5).index.tolist()
    pt_monthly_trajectory = {}
    for pt in top_5_pts:
        subset = rxn_df[rxn_df["pt"] == pt]
        pt_counts = subset["_month"].value_counts().sort_index().to_dict()
        pt_monthly_trajectory[pt] = {str(k): int(v) for k, v in pt_counts.items() if k != "NaT"}

    metrics.append(EvidenceMetric(
        evidence_id="TIME-PT-TRAJECTORY",
        metric_name="top_5_pts_monthly_trajectories",
        value=pt_monthly_trajectory,
        unit="reactions",
        source_fields=["receivedate", "patient_reaction_reactionmeddrapt"],
        calculation_definition="Monthly frequency trajectory for top 5 Preferred Terms",
        scope="reaction-level",
        notes="Factual temporal observations only. Statistical variations are not designated as safety signals."
    ))

    return AnalysisSectionResult(
        section_id="trend_analysis",
        section_title="Reporting Volume and Temporal Trend Analysis",
        metrics=metrics,
        metadata={
            "reporting_start": start_date,
            "reporting_end": end_date,
            "duration_days": duration_days
        }
    )
