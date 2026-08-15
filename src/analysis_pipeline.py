"""
Analysis Pipeline: Master deterministic analysis orchestrator for GenAR PADER.

Executes data loading, validation, normalization, and all domain analysis modules
producing a typed, serialized CompleteAnalysisPackage ready for Phase 3.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import PRODUCT_NAME, REPORT_OUTPUT_DIR
from src.data_loader import load_dataset_pipeline, DatasetContainer
from src.validator import validate_dataset
from src.case_analysis import analyze_cases
from src.demographic_analysis import analyze_demographics
from src.reaction_analysis import analyze_reactions
from src.outcome_analysis import analyze_outcomes
from src.trend_analysis import analyze_trends
from src.alert_analysis import analyze_alerts
from src.evidence_model import CompleteAnalysisPackage, ValidationSummary


def run_deterministic_analysis_pipeline(
    filepath: str | Path | None = None,
    output_dir: str | Path | None = None
) -> CompleteAnalysisPackage:
    """
    Run the end-to-end deterministic analysis pipeline.

    Args:
        filepath: Path to dataset file (CSV or XLSX).
        output_dir: Directory to save serialized evidence and validation outputs.

    Returns:
        CompleteAnalysisPackage containing all validated metrics.
    """
    out_dir = Path(output_dir or (REPORT_OUTPUT_DIR / "evidence"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Ingestion & Deduplication
    container: DatasetContainer = load_dataset_pipeline(filepath)

    # 2. Validation Diagnostics
    validation_summary: ValidationSummary = validate_dataset(
        raw_df=container.raw_df,
        normalized_df=container.normalized_df,
        dataset_file=container.file_path.name
    )

    # 3. Domain Analysis Modules (Pure Python)
    case_res = analyze_cases(container.dedup_df)
    demo_res = analyze_demographics(container.dedup_df)
    rxn_res = analyze_reactions(container.dedup_df)
    outcome_res = analyze_outcomes(container.dedup_df)
    trend_res = analyze_trends(container.dedup_df)
    alert_res = analyze_alerts(container.dedup_df)

    sections = {
        "case_analysis": case_res,
        "demographic_analysis": demo_res,
        "reaction_analysis": rxn_res,
        "outcome_analysis": outcome_res,
        "trend_analysis": trend_res,
        "alert_analysis": alert_res,
    }

    # Extract reporting period interval
    period_metric = trend_res.get_metric("TIME-PERIOD-001")
    reporting_period = period_metric.value if period_metric else {}

    # 4. Package into Master Evidence Container
    package = CompleteAnalysisPackage(
        product_name=PRODUCT_NAME,
        reporting_period=reporting_period,
        validation_summary=validation_summary,
        sections=sections
    )

    # 5. Serialize Outputs for Phase 3 and Audit
    summary_file = out_dir / "validation_summary.json"
    summary_file.write_text(validation_summary.model_dump_json(indent=2), encoding="utf-8")

    complete_file = out_dir / "complete_analysis_package.json"
    complete_file.write_text(package.model_dump_json(indent=2), encoding="utf-8")

    # Serialize individual domain files
    for sec_id, sec_obj in sections.items():
        sec_file = out_dir / f"{sec_id}.json"
        sec_file.write_text(sec_obj.model_dump_json(indent=2), encoding="utf-8")

    return package


def print_analysis_summary(package: CompleteAnalysisPackage) -> None:
    """Print a clean, structured summary of the analysis findings to stdout."""
    val = package.validation_summary
    case_sec = package.sections.get("case_analysis")
    demo_sec = package.sections.get("demographic_analysis")
    rxn_sec = package.sections.get("reaction_analysis")
    trend_sec = package.sections.get("trend_analysis")
    alert_sec = package.sections.get("alert_analysis")

    print("\n" + "=" * 78)
    print(f"  GENAR PADER DETERMINISTIC ANALYSIS SUMMARY: {package.product_name}")
    print("=" * 78)

    # Dataset & Validation
    print(f"\n[1] DATASET & VALIDATION:")
    print(f"  - Source File: {val.dataset_file}")
    print(f"  - Total Raw Records: {val.total_raw_rows:,}")
    print(f"  - Total Unique Cases: {val.unique_cases:,} (Latest safetyreportversion deduplication)")
    print(f"  - Duplicate Version Rows Removed: {val.duplicate_rows_count:,}")
    print(f"  - Validation Health Status: [{val.validation_status}]")
    if val.structural_discrepancies:
        print("  - Diagnostic Observations:")
        for disc in val.structural_discrepancies:
            print(f"    * {disc}")

    # Reporting Period & Cases
    p_info = package.reporting_period
    print(f"\n[2] REPORTING INTERVAL & CASE VOLUMES:")
    print(f"  - Reporting Period: {p_info.get('start_date')} to {p_info.get('end_date')} ({p_info.get('duration_days')} days)")
    if case_sec:
        tot = case_sec.get_metric("CO-001")
        ser = case_sec.get_metric("CO-002")
        ser_pct = case_sec.get_metric("CO-003")
        nser = case_sec.get_metric("CO-004")
        exp = alert_sec.get_metric("ALERT-001") if alert_sec else None
        print(f"  - Total Unique Cases: {tot.value if tot else 'N/A'}")
        print(f"  - Serious Cases: {ser.value if ser else 'N/A'} ({ser_pct.value if ser_pct else 'N/A'}%)")
        print(f"  - Non-Serious Cases: {nser.value if nser else 'N/A'}")
        print(f"  - 15-Day Expedited Cases: {exp.value if exp else 'N/A'}")

    # Demographics
    if demo_sec:
        sex_m = demo_sec.get_metric("DEMO-SEX-ALL")
        age_s = demo_sec.get_metric("DEMO-AGE-STATS")
        geo_s = demo_sec.get_metric("DEMO-GEO-ALL")
        print(f"\n[3] PATIENT DEMOGRAPHICS & GEOGRAPHY:")
        if sex_m and isinstance(sex_m.value, dict):
            print(f"  - Sex: Female = {sex_m.value.get('female', {}).get('count')}, "
                  f"Male = {sex_m.value.get('male', {}).get('count')}, "
                  f"Unknown = {sex_m.value.get('unknown', {}).get('count')}")
        if age_s and isinstance(age_s.value, dict):
            print(f"  - Age (in years): Mean = {age_s.value.get('mean')}, Median = {age_s.value.get('median')} "
                  f"(Range: {age_s.value.get('min')} - {age_s.value.get('max')} years)")
        if geo_s and isinstance(geo_s.value, dict):
            top_countries = list(geo_s.value.items())[:5]
            top_c_str = ", ".join([f"{k}: {v.get('count')}" for k, v in top_countries])
            print(f"  - Top Reporting Countries (primarysourcecountry): {top_c_str}")

    # Reactions
    if rxn_sec:
        tot_rxn = rxn_sec.get_metric("RXN-001")
        u_pts = rxn_sec.get_metric("RXN-002")
        top_table = rxn_sec.get_metric("RXN-TOP20-TABLE")
        print(f"\n[4] ADVERSE REACTIONS (MedDRA Preferred Terms):")
        print(f"  - Total Reaction Occurrences: {tot_rxn.value if tot_rxn else 'N/A':,}")
        print(f"  - Distinct Preferred Terms (PTs): {u_pts.value if u_pts else 'N/A':,}")
        print(f"  - Top 5 Preferred Terms (Occurrences | Distinct Cases):")
        if top_table and isinstance(top_table.value, list):
            for item in top_table.value[:5]:
                print(f"    * {item['rank']}. {item['preferred_term']}: {item['total_occurrences']} occurrences across {item['distinct_case_count']} cases ({item['percentage_of_cases']}%)")

    # Drug Characterization
    if case_sec:
        role_m = case_sec.get_metric("DC-ROLE-001")
        if role_m and isinstance(role_m.value, dict):
            print(f"\n[5] DRUG CHARACTERIZATION ROLE ({PRODUCT_NAME}):")
            for role, data in role_m.value.items():
                print(f"  - {role.title()}: {data.get('count')} cases ({data.get('percentage')}%)")

    # Regulatory & Actions
    if alert_sec:
        act_m = alert_sec.get_metric("HIST-ACTION-001")
        exp_m = alert_sec.get_metric("EXPECT-SCOPE-001")
        print(f"\n[6] REGULATORY & SCOPE DECLARATIONS:")
        print(f"  - History of Actions: {'Actions Reported' if act_m and act_m.value.get('actions_reported_in_dataset') else 'No Actions Reported in Dataset'}")
        print(f"  - Expectedness: {'Calculated' if exp_m and exp_m.value.get('expectedness_calculated') else 'Out of Scope (No CCDS supplied)'}")

    print("\n" + "=" * 78)
    print("  DETERMINISTIC ANALYSIS PIPELINE COMPLETED SUCCESSFULLY")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    pkg = run_deterministic_analysis_pipeline()
    print_analysis_summary(pkg)
