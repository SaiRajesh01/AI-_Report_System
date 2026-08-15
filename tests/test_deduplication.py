"""
Tests for canonical case deduplication.
"""
import pytest
import pandas as pd

from src.data_loader import load_raw_data, normalize_data, deduplicate_cases
from src.config import DATASET_PATH


@pytest.fixture
def raw_df():
    df, _ = load_raw_data(DATASET_PATH)
    return df


@pytest.fixture
def dedup_df(raw_df):
    normalized = normalize_data(raw_df)
    return deduplicate_cases(normalized)


class TestDeduplication:
    """Tests for case-level deduplication."""

    def test_unique_case_count(self, dedup_df):
        """Must produce exactly 1,024 unique cases."""
        assert len(dedup_df) == 1024

    def test_no_duplicate_safetyreportids(self, dedup_df):
        """No duplicate safetyreportid values should remain."""
        assert dedup_df["safetyreportid"].is_unique

    def test_keeps_latest_version(self, raw_df, dedup_df):
        """For each case, the latest version should be kept."""
        # Find a case with multiple versions
        vc = raw_df["safetyreportid"].value_counts()
        multi = int(vc[vc > 1].index[0])

        # Get the max version from raw
        max_version = int(raw_df[raw_df["safetyreportid"].astype(str) == str(multi)]["safetyreportversion"].astype(int).max())

        # Check that dedup kept the max version
        dedup_version = int(dedup_df[dedup_df["safetyreportid"] == multi]["safetyreportversion"].iloc[0])
        assert dedup_version == max_version

    def test_dedup_summary(self, raw_df, dedup_df):
        """Dedup summary should report correct numbers."""
        assert len(raw_df) == 1068
        assert len(dedup_df) == 1024
        assert len(raw_df) - len(dedup_df) == 44

    def test_dedup_missing_column_raises(self):
        """Should raise if safetyreportid column is missing."""
        df = pd.DataFrame({"other_col": [1, 2]})
        with pytest.raises(ValueError, match="safetyreportid"):
            deduplicate_cases(df)
