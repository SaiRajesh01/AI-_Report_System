"""
Case Analysis Module: Case-level counts, seriousness breakdown, report types,
reporter qualifications, and drug characterization roles.
"""
from __future__ import annotations

import pandas as pd
from src.evidence_model import EvidenceMetric, AnalysisSectionResult
from src.config import PRODUCT_NAME


def analyze_cases(dedup_df: pd.DataFrame) -> AnalysisSectionResult:
    """
    Perform deterministic case-level analysis on deduplicated case dataset.

    Returns:
        AnalysisSectionResult containing structured EvidenceMetrics.
    """
    total_cases = len(dedup_df)
    metrics: list[EvidenceMetric] = []

    # 1. Total Unique Cases
    metrics.append(EvidenceMetric(
        evidence_id="CO-001",
        metric_name="total_unique_cases",
        value=total_cases,
        unit="cases",
        source_fields=["safetyreportid", "safetyreportversion"],
        calculation_definition="COUNT(DISTINCT safetyreportid) taking the highest safetyreportversion",
        scope="case-level",
        supporting_case_ids=dedup_df["safetyreportid"].tolist()[:10]
    ))

    # 2. Serious Cases
    serious_count = int((dedup_df["serious"] == "serious").sum())
    serious_pct = round((serious_count / total_cases * 100), 2) if total_cases > 0 else 0.0
    metrics.append(EvidenceMetric(
        evidence_id="CO-002",
        metric_name="serious_cases_count",
        value=serious_count,
        unit="cases",
        source_fields=["serious"],
        calculation_definition="COUNT(cases WHERE serious == 'serious')",
        scope="case-level"
    ))
    metrics.append(EvidenceMetric(
        evidence_id="CO-003",
        metric_name="serious_cases_percentage",
        value=serious_pct,
        unit="%",
        source_fields=["serious"],
        calculation_definition="(serious_cases_count / total_unique_cases) * 100",
        scope="case-level"
    ))

    # 3. Non-Serious Cases
    non_serious_count = int((dedup_df["serious"] == "not serious").sum())
    non_serious_pct = round((non_serious_count / total_cases * 100), 2) if total_cases > 0 else 0.0
    metrics.append(EvidenceMetric(
        evidence_id="CO-004",
        metric_name="non_serious_cases_count",
        value=non_serious_count,
        unit="cases",
        source_fields=["serious"],
        calculation_definition="COUNT(cases WHERE serious == 'not serious')",
        scope="case-level"
    ))
    metrics.append(EvidenceMetric(
        evidence_id="CO-005",
        metric_name="non_serious_cases_percentage",
        value=non_serious_pct,
        unit="%",
        source_fields=["serious"],
        calculation_definition="(non_serious_cases_count / total_unique_cases) * 100",
        scope="case-level"
    ))

    # 4. Seriousness Criteria Reason Flags
    criteria_map = {
        "seriousnessdeath": ("Death (Fatal)", "SER-001"),
        "seriousnesslifethreatening": ("Life-threatening", "SER-002"),
        "seriousnesshospitalization": ("Hospitalization / Prolonged", "SER-003"),
        "seriousnessdisabling": ("Disability / Incapacity", "SER-004"),
        "seriousnesscongenitalanomali": ("Congenital Anomaly", "SER-005"),
        "seriousnessother": ("Other Medically Important", "SER-006"),
    }
    criteria_summary = {}
    for col, (label, ev_id) in criteria_map.items():
        if col in dedup_df.columns:
            count = int((dedup_df[col] == "yes").sum())
            pct = round(count / total_cases * 100, 2) if total_cases > 0 else 0.0
            criteria_summary[label] = {"count": count, "percentage": pct}
            metrics.append(EvidenceMetric(
                evidence_id=ev_id,
                metric_name=f"seriousness_criterion_{col}",
                value={"criterion": label, "count": count, "percentage": pct},
                unit="cases",
                source_fields=[col],
                calculation_definition=f"COUNT(cases WHERE {col} == 'yes')",
                scope="case-level",
                notes="Seriousness criteria are independent, non-mutually exclusive flags."
            ))

    metrics.append(EvidenceMetric(
        evidence_id="SER-SUMMARY",
        metric_name="seriousness_criteria_breakdown",
        value=criteria_summary,
        unit=None,
        source_fields=list(criteria_map.keys()),
        calculation_definition="Aggregation of independent seriousness criteria flags",
        scope="case-level"
    ))

    # Multi-criteria analysis
    criteria_cols = [c for c in criteria_map.keys() if c in dedup_df.columns]
    criteria_sum = dedup_df[criteria_cols].apply(lambda x: x == "yes").sum(axis=1)
    multi_criteria_dict = {
        "1_criterion": int((criteria_sum == 1).sum()),
        "2_criteria": int((criteria_sum == 2).sum()),
        "3_or_more_criteria": int((criteria_sum >= 3).sum()),
    }
    metrics.append(EvidenceMetric(
        evidence_id="SER-MULTI",
        metric_name="multi_criteria_distribution",
        value=multi_criteria_dict,
        unit="cases",
        source_fields=criteria_cols,
        calculation_definition="Count of cases meeting 1, 2, or >=3 criteria simultaneously",
        scope="case-level"
    ))

    # 5. Report Type Distribution
    if "reporttype" in dedup_df.columns:
        rt_counts = dedup_df["reporttype"].fillna("unknown").value_counts().to_dict()
        rt_summary = {str(k): {"count": int(v), "percentage": round(int(v) / total_cases * 100, 2)} for k, v in rt_counts.items()}
        metrics.append(EvidenceMetric(
            evidence_id="CO-RT-001",
            metric_name="report_type_distribution",
            value=rt_summary,
            unit="cases",
            source_fields=["reporttype"],
            calculation_definition="GROUP BY reporttype -> count and percentage",
            scope="case-level"
        ))

    # 6. Primary Reporter Qualification
    if "primarysource_qualification" in dedup_df.columns:
        qual_counts = dedup_df["primarysource_qualification"].fillna("unknown").value_counts().to_dict()
        qual_summary = {str(k): {"count": int(v), "percentage": round(int(v) / total_cases * 100, 2)} for k, v in qual_counts.items()}
        metrics.append(EvidenceMetric(
            evidence_id="CO-QUAL-001",
            metric_name="reporter_qualification_distribution",
            value=qual_summary,
            unit="cases",
            source_fields=["primarysource_qualification"],
            calculation_definition="GROUP BY primarysource_qualification -> count and percentage",
            scope="case-level"
        ))

    # 7. Drug Characterization for Bisoprolol
    product_lower = PRODUCT_NAME.lower()
    biso_roles: list[str] = []
    for _, row in dedup_df.iterrows():
        drug_names = str(row.get("patient_drug_medicinalproduct", "")).split(",")
        chars = str(row.get("patient_drug_drugcharacterization", "")).split(",")
        matched_role = "unknown"
        for d, c in zip(drug_names, chars):
            if product_lower in d.strip().lower():
                matched_role = c.strip().lower()
                break
        biso_roles.append(matched_role)

    role_counts = pd.Series(biso_roles).value_counts().to_dict()
    role_summary = {
        str(k): {"count": int(v), "percentage": round(int(v) / total_cases * 100, 2)}
        for k, v in role_counts.items()
    }
    metrics.append(EvidenceMetric(
        evidence_id="DC-ROLE-001",
        metric_name="bisoprolol_role_distribution",
        value=role_summary,
        unit="cases",
        source_fields=["patient_drug_medicinalproduct", "patient_drug_drugcharacterization"],
        calculation_definition=f"Extracted characterization role for '{PRODUCT_NAME}' across all cases",
        scope="case-level",
        notes="Highlights suspect vs concomitant vs interacting distribution."
    ))

    return AnalysisSectionResult(
        section_id="case_analysis",
        section_title="Case Volume and Seriousness Analysis",
        metrics=metrics,
        metadata={"total_cases_analyzed": total_cases}
    )


analyze_case_overview = analyze_cases
