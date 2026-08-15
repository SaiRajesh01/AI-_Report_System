"""
Tests for canonical data loading and validation.
"""
import pytest
import pandas as pd
from pathlib import Path

from src.data_loader import load_raw_data, resolve_dataset_path, DataLoadError
from src.validator import validate_dataset_schema
from src.config import DATASET_PATH


class TestLoader:
    """Tests for the canonical dataset loader."""

    def test_load_dataset_exists(self):
        """The dataset file should exist at the configured path."""
        resolved = resolve_dataset_path(DATASET_PATH)
        assert resolved.exists(), f"Dataset not found at {resolved}"

    def test_load_dataset_returns_dataframe(self):
        """Loading should return a pandas DataFrame."""
        df, _ = load_raw_data(DATASET_PATH)
        assert isinstance(df, pd.DataFrame)

    def test_load_dataset_has_rows(self):
        """Dataset should have exactly 1,068 rows."""
        df, _ = load_raw_data(DATASET_PATH)
        assert len(df) == 1068

    def test_load_dataset_has_columns(self):
        """Dataset should have 67 columns."""
        df, _ = load_raw_data(DATASET_PATH)
        assert len(df.columns) == 67

    def test_load_nonexistent_file_raises(self):
        """Loading a nonexistent file should raise DataLoadError."""
        with pytest.raises(DataLoadError, match="not found"):
            load_raw_data("nonexistent_file.csv")

    def test_validate_schema_passes(self):
        """Schema validation should pass for the real dataset."""
        df, _ = load_raw_data(DATASET_PATH)
        missing = validate_dataset_schema(df)
        assert missing == []

    def test_validate_schema_missing_column(self):
        """Schema validation should fail if a required column is missing."""
        df = pd.DataFrame({"col1": [1, 2, 3]})
        missing = validate_dataset_schema(df)
        assert len(missing) > 0
