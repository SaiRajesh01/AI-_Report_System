"""
Demographic Analysis Module: Patient age groups, summary statistics, sex distribution,
and geographic origin with explicit country field selection documentation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.evidence_model import EvidenceMetric, AnalysisSectionResult
from src.config import AGE_GROUP_BINS, AGE_GROUP_LABELS, COUNTRY_CODE_MAP


def convert_onset_age_to_years(df: pd.DataFrame) -> pd.Series:
    """
    Convert patient_patientonsetage to standard numeric years based on patient_patientonsetageunit.

    Supported units:
      - year: age as-is
      - month: age / 12.0
      - week: age / 52.18
      - day: age / 365.25
      - 800 (FAERS code for decade): age * 10.0
    """
    age = pd.to_numeric(df["patient_patientonsetage"], errors="coerce")
    unit = df["patient_patientonsetageunit"].fillna("").astype(str).str.lower().str.strip()

    age_years = pd.Series(np.nan, index=df.index, dtype=float)

    # Unit mappings
    age_years[unit == "year"] = age[unit == "year"]
    age_years[unit == "month"] = age[unit == "month"] / 12.0
    age_years[unit == "week"] = age[unit == "week"] / 52.18
    age_years[unit == "day"] = age[unit == "day"] / 365.25
    age_years[unit == "800"] = age[unit == "800"] * 10.0

    return age_years


def analyze_demographics(dedup_df: pd.DataFrame) -> AnalysisSectionResult:
    """
    Perform deterministic demographic analysis on deduplicated cases.

    Returns:
        AnalysisSectionResult containing structured EvidenceMetrics.
    """
    total_cases = len(dedup_df)
    metrics: list[EvidenceMetric] = []

    # ── 1. Sex Distribution ──────────────────────────────────────────────────
    sex_series = dedup_df["patient_patientsex"].fillna("unknown").astype(str).str.lower().str.strip()
    sex_counts = sex_series.value_counts().to_dict()
    sex_summary = {}
    for sex_key in ["female", "male", "unknown"]:
        count = int(sex_counts.get(sex_key, 0))
        pct = round(count / total_cases * 100, 2) if total_cases > 0 else 0.0
        sex_summary[sex_key] = {"count": count, "percentage": pct}
        metrics.append(EvidenceMetric(
            evidence_id=f"DEMO-SEX-{sex_key.upper()}",
            metric_name=f"sex_count_{sex_key}",
            value={"count": count, "percentage": pct},
            unit="cases",
            source_fields=["patient_patientsex"],
            calculation_definition=f"COUNT(cases WHERE patient_patientsex == '{sex_key}')",
            scope="case-level"
        ))

    metrics.append(EvidenceMetric(
        evidence_id="DEMO-SEX-ALL",
        metric_name="sex_distribution_breakdown",
        value=sex_summary,
        unit="cases",
        source_fields=["patient_patientsex"],
        calculation_definition="Complete sex breakdown with percentages",
        scope="case-level"
    ))

    # ── 2. Age Analysis & Bucketing ──────────────────────────────────────────
    age_years = convert_onset_age_to_years(dedup_df)
    valid_ages = age_years.dropna()
    valid_age_count = len(valid_ages)
    missing_age_count = total_cases - valid_age_count

    stats_dict = {}
    if valid_age_count > 0:
        stats_dict = {
            "count_with_age": valid_age_count,
            "count_missing_age": missing_age_count,
            "mean": round(float(valid_ages.mean()), 2),
            "median": round(float(valid_ages.median()), 2),
            "min": round(float(valid_ages.min()), 2),
            "max": round(float(valid_ages.max()), 2),
            "std": round(float(valid_ages.std()), 2),
        }
        metrics.append(EvidenceMetric(
            evidence_id="DEMO-AGE-STATS",
            metric_name="patient_age_summary_statistics",
            value=stats_dict,
            unit="years",
            source_fields=["patient_patientonsetage", "patient_patientonsetageunit"],
            calculation_definition="Summary statistics on patient age converted to years",
            scope="case-level"
        ))

    # WHO/ICH Age Group Bucketing
    age_groups = pd.cut(valid_ages, bins=AGE_GROUP_BINS, labels=AGE_GROUP_LABELS, right=False)
    group_counts = age_groups.value_counts().to_dict()

    age_group_summary = {}
    for label in AGE_GROUP_LABELS:
        count = int(group_counts.get(label, 0))
        pct = round(count / total_cases * 100, 2) if total_cases > 0 else 0.0
        age_group_summary[label] = {"count": count, "percentage": pct}
        metrics.append(EvidenceMetric(
            evidence_id=f"DEMO-AGEGROUP-{label.upper().replace('/', '_')}",
            metric_name=f"age_group_{label}",
            value={"count": count, "percentage": pct},
            unit="cases",
            source_fields=["patient_patientonsetage", "patient_patientonsetageunit"],
            calculation_definition=f"COUNT(cases WHERE age in bucket '{label}')",
            scope="case-level"
        ))

    age_group_summary["Age Missing / Not Reported"] = {
        "count": missing_age_count,
        "percentage": round(missing_age_count / total_cases * 100, 2) if total_cases > 0 else 0.0
    }

    metrics.append(EvidenceMetric(
        evidence_id="DEMO-AGEGROUP-ALL",
        metric_name="age_group_distribution_breakdown",
        value=age_group_summary,
        unit="cases",
        source_fields=["patient_patientonsetage", "patient_patientonsetageunit"],
        calculation_definition="Complete WHO/ICH age group distribution",
        scope="case-level"
    ))

    # ── 3. Geographic Distribution ───────────────────────────────────────────
    # We explicitly select 'primarysourcecountry' as the primary country field
    # because in E2B/FAERS standards, primarysourcecountry represents the origin of the report.
    country_raw = dedup_df["primarysourcecountry"].fillna("Unknown").astype(str).str.strip()

    # Normalize ISO 2-letter codes and capitalization
    country_normalized = country_raw.replace(COUNTRY_CODE_MAP)
    # Title case except for 'EU'
    country_clean = country_normalized.apply(lambda c: "EU (Regional)" if str(c).lower() == "eu" else str(c).title())

    country_counts = country_clean.value_counts().to_dict()
    country_summary = {
        str(k): {"count": int(v), "percentage": round(int(v) / total_cases * 100, 2)}
        for k, v in country_counts.items()
    }

    metrics.append(EvidenceMetric(
        evidence_id="DEMO-GEO-ALL",
        metric_name="geographic_country_distribution",
        value=country_summary,
        unit="cases",
        source_fields=["primarysourcecountry"],
        calculation_definition="COUNT(cases) GROUP BY primarysourcecountry (normalized)",
        scope="case-level",
        notes="primarysourcecountry is selected as the primary geographic field; ISO 2-letter codes mapped to full country names."
    ))

    return AnalysisSectionResult(
        section_id="demographic_analysis",
        section_title="Patient Demographics and Geographic Distribution",
        metrics=metrics,
        metadata={
            "selected_country_field": "primarysourcecountry",
            "age_conversion_units_handled": ["year", "month", "week", "day", "800 (decade)"]
        }
    )
