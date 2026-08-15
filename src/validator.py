"""
Validator: Comprehensive validation and data hygiene diagnostics for ICSR datasets.

Analyzes missing values, type consistency, date ranges, case duplication,
and data-to-domain discrepancies.
"""
from __future__ import annotations

from typing import Any
import pandas as pd

from src.config import REQUIRED_COLUMNS
from src.evidence_model import ValidationSummary


def validate_dataset(
    raw_df: pd.DataFrame,
    normalized_df: pd.DataFrame,
    dataset_file: str = "Bisoprolol_icsr_sample_1068rows.xlsx"
) -> ValidationSummary:
    """
    Run full suite of validation checks on raw and normalized dataframes.

    Returns:
        ValidationSummary containing diagnostic metrics and data health status.
    """
    total_raw_rows = len(raw_df)
    unique_cases = int(normalized_df["safetyreportid"].nunique()) if "safetyreportid" in normalized_df.columns else 0
    duplicate_rows = total_raw_rows - unique_cases

    # 1. Required columns check
    actual_columns = set(raw_df.columns)
    missing_required = sorted(set(REQUIRED_COLUMNS) - actual_columns)

    # 2. Missing values summary
    missing_summary = {}
    for col in raw_df.columns:
        null_count = int(raw_df[col].isna().sum() + (raw_df[col].astype(str).str.strip().isin(["", "nan", "None"])).sum())
        # Prevent double count if isna already caught it
        null_count = int(raw_df[col].isna().sum())
        pct = round(null_count / total_raw_rows * 100, 2) if total_raw_rows > 0 else 0.0
        missing_summary[col] = {
            "null_count": null_count,
            "null_percentage": pct,
            "non_null_count": total_raw_rows - null_count
        }

    # 3. Date range validation
    if "parsed_receivedate" in normalized_df.columns:
        valid_dates = normalized_df["parsed_receivedate"].dropna()
        start_date = valid_dates.min().strftime("%Y-%m-%d") if len(valid_dates) > 0 else "UNKNOWN"
        end_date = valid_dates.max().strftime("%Y-%m-%d") if len(valid_dates) > 0 else "UNKNOWN"
    else:
        start_date = "UNKNOWN"
        end_date = "UNKNOWN"

    # 4. Column data types in normalized dataset
    column_dtypes = {col: str(normalized_df[col].dtype) for col in normalized_df.columns}

    # 5. Domain Discrepancy & Health Checks
    discrepancies = []

    # A. Case count vs Row count
    if total_raw_rows != unique_cases:
        discrepancies.append(
            f"Row count ({total_raw_rows}) exceeds unique safetyreportid count ({unique_cases}). "
            f"{duplicate_rows} rows represent subsequent version updates (latest version retained for case-level analysis)."
        )

    # B. SOC Column check
    soc_cols = [c for c in raw_df.columns if "soc" in c.lower()]
    if not soc_cols:
        discrepancies.append("No System Organ Class (SOC) column found. Analysis must proceed exclusively at MedDRA Preferred Term (PT) level.")

    # C. Clinical narrative check
    if "patient_summary_narrativeincludeclinical" in raw_df.columns:
        narrs = raw_df["patient_summary_narrativeincludeclinical"].dropna()
        if len(narrs) > 0:
            avg_len = narrs.astype(str).str.len().mean()
            if avg_len < 40:
                discrepancies.append(
                    f"Narrative field contains only date stubs (average length: {avg_len:.1f} chars). "
                    "Clinical narratives cannot be extracted directly from this field."
                )

    # D. Missing age check
    if "patient_patientonsetage" in raw_df.columns:
        missing_age_pct = missing_summary.get("patient_patientonsetage", {}).get("null_percentage", 0.0)
        if missing_age_pct > 0:
            discrepancies.append(f"Patient age is missing in {missing_age_pct}% of records.")

    # Determine status
    if missing_required:
        status = "FAIL"
    elif discrepancies:
        status = "WARNING"
    else:
        status = "PASS"

    return ValidationSummary(
        dataset_file=str(dataset_file),
        total_raw_rows=total_raw_rows,
        unique_cases=unique_cases,
        duplicate_rows_count=duplicate_rows,
        columns_count=len(raw_df.columns),
        required_columns_checked=REQUIRED_COLUMNS,
        missing_required_columns=missing_required,
        date_range_start=start_date,
        date_range_end=end_date,
        missing_value_summary=missing_summary,
        column_dtypes=column_dtypes,
        structural_discrepancies=discrepancies,
        validation_status=status
    )


def validate_dataset_schema(df: pd.DataFrame) -> list[str]:
    """Check for missing required columns in DataFrame."""
    actual_columns = set(df.columns)
    return sorted(set(REQUIRED_COLUMNS) - actual_columns)

