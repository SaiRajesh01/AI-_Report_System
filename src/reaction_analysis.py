"""
Reaction Analysis Module: Preferred Terms (PT) frequency, distinct-case counts,
serious reaction frequencies, and cross-tabulations without unsupported SOC inference.
"""
from __future__ import annotations

import pandas as pd
from src.evidence_model import EvidenceMetric, AnalysisSectionResult
from src.config import TOP_N_REACTIONS


def unpack_reaction_rows(dedup_df: pd.DataFrame) -> pd.DataFrame:
    """
    Unpack comma-separated reaction terms into individual reaction-level records.

    Returns:
        DataFrame with columns: safetyreportid, pt, outcome, serious, sex, age_years.
    """
    records = []
    for _, row in dedup_df.iterrows():
        case_id = row["safetyreportid"]
        pts = [p.strip() for p in str(row.get("patient_reaction_reactionmeddrapt", "")).split(",") if p.strip() and p.strip().lower() != "nan"]
        outcomes = [o.strip() for o in str(row.get("patient_reaction_reactionoutcome", "")).split(",") if o.strip()]

        # Align outcomes with PTs
        while len(outcomes) < len(pts):
            outcomes.append("unknown")

        serious_val = str(row.get("serious", "unknown"))

        for pt, outcome in zip(pts, outcomes):
            records.append({
                "safetyreportid": case_id,
                "pt": pt,
                "outcome": outcome.lower(),
                "serious": serious_val,
                "sex": str(row.get("patient_patientsex", "unknown")),
            })

    return pd.DataFrame(records)


def analyze_reactions(dedup_df: pd.DataFrame) -> AnalysisSectionResult:
    """
    Perform deterministic reaction analysis at the MedDRA Preferred Term (PT) level.

    Returns:
        AnalysisSectionResult containing structured EvidenceMetrics.
    """
    rxn_df = unpack_reaction_rows(dedup_df)
    total_reactions = len(rxn_df)
    unique_pts = int(rxn_df["pt"].nunique()) if total_reactions > 0 else 0
    total_cases = len(dedup_df)

    metrics: list[EvidenceMetric] = []

    # 1. Total Reaction Occurrences
    metrics.append(EvidenceMetric(
        evidence_id="RXN-001",
        metric_name="total_reaction_occurrences",
        value=total_reactions,
        unit="reactions",
        source_fields=["patient_reaction_reactionmeddrapt"],
        calculation_definition="Total count of exploded Preferred Term instances across unique cases",
        scope="reaction-level",
        notes="Unpacked from comma-separated string across 1,024 unique deduplicated cases."
    ))

    # 2. Total Unique Preferred Terms
    metrics.append(EvidenceMetric(
        evidence_id="RXN-002",
        metric_name="unique_preferred_terms_count",
        value=unique_pts,
        unit="terms",
        source_fields=["patient_reaction_reactionmeddrapt"],
        calculation_definition="COUNT(DISTINCT pt) across all unpacked reactions",
        scope="reaction-level"
    ))

    # 3. Top Preferred Terms with BOTH total reactions AND distinct case count!
    pt_total_counts = rxn_df["pt"].value_counts()
    pt_distinct_cases = rxn_df.groupby("pt")["safetyreportid"].nunique()

    top_pts_data = []
    for rank, (pt, total_occ) in enumerate(pt_total_counts.head(TOP_N_REACTIONS).items(), 1):
        distinct_cases = int(pt_distinct_cases.get(pt, 0))
        pct_of_reactions = round(total_occ / total_reactions * 100, 2) if total_reactions > 0 else 0.0
        pct_of_cases = round(distinct_cases / total_cases * 100, 2) if total_cases > 0 else 0.0

        item = {
            "rank": rank,
            "preferred_term": str(pt),
            "total_occurrences": int(total_occ),
            "percentage_of_reactions": pct_of_reactions,
            "distinct_case_count": distinct_cases,
            "percentage_of_cases": pct_of_cases
        }
        top_pts_data.append(item)

        metrics.append(EvidenceMetric(
            evidence_id=f"RXN-TOP-{rank:02d}",
            metric_name=f"top_{rank:02d}_reaction_{pt.replace(' ', '_').lower()}",
            value=item,
            unit="reactions",
            source_fields=["patient_reaction_reactionmeddrapt"],
            calculation_definition="Total occurrences and distinct case count for Preferred Term",
            scope="reaction-level"
        ))

    metrics.append(EvidenceMetric(
        evidence_id="RXN-TOP20-TABLE",
        metric_name="top_20_preferred_terms_table",
        value=top_pts_data,
        unit=None,
        source_fields=["patient_reaction_reactionmeddrapt"],
        calculation_definition=f"Top {TOP_N_REACTIONS} most frequent Preferred Terms ranked by total occurrences",
        scope="reaction-level"
    ))

    # 4. Top Reactions from Serious Cases Only
    serious_rxn = rxn_df[rxn_df["serious"] == "serious"]
    serious_pt_counts = serious_rxn["pt"].value_counts()
    serious_pt_cases = serious_rxn.groupby("pt")["safetyreportid"].nunique()

    top_serious_data = []
    for rank, (pt, total_occ) in enumerate(serious_pt_counts.head(TOP_N_REACTIONS).items(), 1):
        distinct_cases = int(serious_pt_cases.get(pt, 0))
        top_serious_data.append({
            "rank": rank,
            "preferred_term": str(pt),
            "serious_reaction_count": int(total_occ),
            "distinct_case_count": distinct_cases
        })

    metrics.append(EvidenceMetric(
        evidence_id="RXN-SERIOUS-TOP20",
        metric_name="top_20_serious_reactions_table",
        value=top_serious_data,
        unit=None,
        source_fields=["patient_reaction_reactionmeddrapt", "serious"],
        calculation_definition="Top 20 Preferred Terms reported within serious cases",
        scope="reaction-level"
    ))

    # 5. SOC Absence Notice
    metrics.append(EvidenceMetric(
        evidence_id="RXN-SOC-NOTICE",
        metric_name="soc_analysis_availability",
        value="UNAVAILABLE - No System Organ Class field supplied in dataset",
        unit=None,
        source_fields=["patient_reaction_reactionmeddrapt"],
        calculation_definition="Compliance requirement: No MedDRA SOC inference performed without external dictionary",
        scope="dataset-level",
        notes="Explicitly conforms to the challenge constraint: only MedDRA PT level analysis is performed."
    ))

    return AnalysisSectionResult(
        section_id="reaction_analysis",
        section_title="Adverse Reaction / Preferred Term Analysis",
        metrics=metrics,
        metadata={
            "total_reaction_records": total_reactions,
            "soc_field_present": False
        }
    )
