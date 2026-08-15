"""
Data Loader: Safe loading, normalization, and deduplication of ICSR safety data.

Preserves the raw dataset unmutated in memory and produces a normalized, typed
DataFrame alongside a deduplicated case-level DataFrame.
"""
from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from typing import Any
import numpy as np
import pandas as pd

from src.config import REQUIRED_COLUMNS, DATASET_PATH


class DataLoadError(Exception):
    """Raised when data loading fails."""
    pass


@dataclass
class DatasetContainer:
    """Encapsulates raw, normalized, and deduplicated case-level datasets."""
    raw_df: pd.DataFrame
    normalized_df: pd.DataFrame
    dedup_df: pd.DataFrame
    file_path: Path
    total_raw_rows: int
    unique_cases: int
    duplicate_rows_removed: int


def resolve_dataset_path(filepath: str | Path | None = None) -> Path:
    """Resolve the dataset file path, falling back between .csv and .xlsx if needed."""
    if filepath is None:
        target = DATASET_PATH
    else:
        target = Path(filepath)

    if target.exists():
        return target

    # Try looking in project root if relative path
    if not target.is_absolute():
        alt = Path(__file__).resolve().parent.parent / target
        if alt.exists():
            return alt

    # If .csv was requested but only .xlsx exists (or vice-versa)
    if target.suffix.lower() == ".csv":
        xlsx_alt = target.with_suffix(".xlsx")
        if xlsx_alt.exists():
            return xlsx_alt
    elif target.suffix.lower() in (".xlsx", ".xls"):
        csv_alt = target.with_suffix(".csv")
        if csv_alt.exists():
            return csv_alt

    raise DataLoadError(f"Dataset file not found at: {target}")


def load_raw_data(filepath: str | Path | None = None) -> tuple[pd.DataFrame, Path]:
    """
    Safely load the raw dataset without modifying column types or values.

    Returns:
        Tuple of (raw_dataframe_copy, resolved_filepath).
    """
    resolved_path = resolve_dataset_path(filepath)
    ext = resolved_path.suffix.lower()

    try:
        if ext == ".csv":
            df_raw = pd.read_csv(resolved_path, dtype=str)
        elif ext in (".xlsx", ".xls"):
            df_raw = pd.read_excel(resolved_path, engine="openpyxl", dtype=str)
        else:
            raise DataLoadError(f"Unsupported file format: {ext}. Expected .csv or .xlsx")
    except Exception as e:
        raise DataLoadError(f"Failed to read dataset from {resolved_path}: {e}") from e

    if df_raw.empty:
        raise DataLoadError("Dataset is empty (0 rows).")

    return df_raw.copy(), resolved_path


def normalize_data(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize raw data: trim whitespace, parse numeric IDs and metrics,
    normalize strings to lowercase where appropriate, without modifying raw_df.
    """
    df = raw_df.copy()

    # Clean column names
    df.columns = [str(c).strip() for c in df.columns]

    # Convert safetyreportid and version to integers
    if "safetyreportid" in df.columns:
        df["safetyreportid"] = pd.to_numeric(df["safetyreportid"], errors="coerce").fillna(0).astype(int)

    if "safetyreportversion" in df.columns:
        df["safetyreportversion"] = pd.to_numeric(df["safetyreportversion"], errors="coerce").fillna(1).astype(int)

    # Standardize string categorical fields
    string_cols = [
        "serious", "seriousnessdeath", "seriousnesslifethreatening",
        "seriousnesshospitalization", "seriousnessdisabling",
        "seriousnesscongenitalanomali", "seriousnessother",
        "fulfillexpeditecriteria", "reporttype", "patient_patientsex",
        "primarysource_qualification", "primarysourcecountry", "occurcountry"
    ]
    for col in string_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.lower()
            df[col] = df[col].replace({"nan": np.nan, "none": np.nan, "": np.nan})

    # Numeric age
    if "patient_patientonsetage" in df.columns:
        df["patient_patientonsetage"] = pd.to_numeric(df["patient_patientonsetage"], errors="coerce")

    if "patient_patientonsetageunit" in df.columns:
        df["patient_patientonsetageunit"] = (
            df["patient_patientonsetageunit"].astype(str).str.strip().str.lower()
            .replace({"nan": np.nan, "none": np.nan, "": np.nan})
        )

    # Dates: receivedate, receiptdate, transmissiondate
    date_cols = ["receivedate", "receiptdate", "transmissiondate"]
    for col in date_cols:
        if col in df.columns:
            df[f"parsed_{col}"] = pd.to_datetime(
                df[col].astype(str).str.replace(".0", "", regex=False),
                format="%Y%m%d",
                errors="coerce"
            )

    return df


def deduplicate_cases(normalized_df: pd.DataFrame) -> pd.DataFrame:
    """
    Deduplicate cases by keeping the latest safetyreportversion for each unique safetyreportid.
    """
    if "safetyreportid" not in normalized_df.columns:
        raise ValueError("safetyreportid is required for case-level deduplication")

    sort_cols = ["safetyreportid"]
    if "safetyreportversion" in normalized_df.columns:
        sort_cols.append("safetyreportversion")

    df_sorted = normalized_df.sort_values(by=sort_cols, ascending=[True, False])
    df_dedup = df_sorted.drop_duplicates(subset=["safetyreportid"], keep="first").reset_index(drop=True)

    return df_dedup


def load_dataset_pipeline(filepath: str | Path | None = None) -> DatasetContainer:
    """
    Full data ingestion entry point: loads raw data, creates normalized DataFrame,
    and produces deduplicated case-level DataFrame.
    """
    raw_df, resolved_path = load_raw_data(filepath)
    normalized_df = normalize_data(raw_df)
    dedup_df = deduplicate_cases(normalized_df)

    return DatasetContainer(
        raw_df=raw_df,
        normalized_df=normalized_df,
        dedup_df=dedup_df,
        file_path=resolved_path,
        total_raw_rows=len(raw_df),
        unique_cases=len(dedup_df),
        duplicate_rows_removed=len(raw_df) - len(dedup_df)
    )
