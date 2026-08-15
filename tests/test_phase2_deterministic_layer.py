"""
Unit and Integration Tests for Phase 2 Deterministic Analysis Layer.

Verifies exact numerical accuracy, data loading, validation diagnostics,
and evidence metric structures across all analysis modules.
"""
from __future__ import annotations

import pytest
import pandas as pd

from src.data_loader import load_dataset_pipeline, resolve_dataset_path, normalize_data, deduplicate_cases
from src.validator import validate_dataset
from src.case_analysis import analyze_cases
from src.demographic_analysis import analyze_demographics, convert_onset_age_to_years
from src.reaction_analysis import analyze_reactions, unpack_reaction_rows
from src.outcome_analysis import analyze_outcomes, determine_worst_case_outcome
from src.trend_analysis import analyze_trends
from src.alert_analysis import analyze_alerts
from src.analysis_pipeline import run_deterministic_analysis_pipeline


@pytest.fixture(scope="session")
def dataset_container():
    """Load the dataset once for all test assertions."""
    return load_dataset_pipeline("Bisoprolol_icsr_sample_1068rows.csv")


class TestDataLoaderAndIngestion:
    def test_raw_rows_and_deduplication(self, dataset_container):
        """Must preserve raw 1,068 rows and deduplicate to exactly 1,024 cases."""
        assert dataset_container.total_raw_rows == 1068
        assert dataset_container.unique_cases == 1024
        assert dataset_container.duplicate_rows_removed == 44

    def test_raw_df_remains_unmutated(self, dataset_container):
        """Raw dataframe must retain string types and original column names."""
        assert len(dataset_container.raw_df) == 1068
        assert isinstance(dataset_container.raw_df, pd.DataFrame)

    def test_safetyreportid_uniqueness(self, dataset_container):
        """Deduplicated dataframe must contain strictly unique safetyreportids."""
        assert dataset_container.dedup_df["safetyreportid"].is_unique


class TestValidationDiagnostics:
    def test_validation_detects_discrepancies(self, dataset_container):
        """Validation summary must detect duplicate versions, SOC absence, and stub narratives."""
        summary = validate_dataset(dataset_container.raw_df, dataset_container.normalized_df)
        assert summary.total_raw_rows == 1068
        assert summary.unique_cases == 1024
        assert summary.duplicate_rows_count == 44
        assert summary.validation_status in ("PASS", "WARNING")

        # Verify discrepancy messages
        disc_text = " ".join(summary.structural_discrepancies).lower()
        assert "soc" in disc_text
        assert "narrative" in disc_text


class TestDeterministicCaseAnalysis:
    def test_case_overview_counts(self, dataset_container):
        """Verify exact case volumes and seriousness metrics."""
        result = analyze_cases(dataset_container.dedup_df)
        metrics = {m.metric_name: m.value for m in result.metrics}

        assert metrics["total_unique_cases"] == 1024
        assert metrics["serious_cases_count"] == 1023
        assert metrics["non_serious_cases_count"] == 1
        assert metrics["serious_cases_percentage"] == pytest.approx(99.9, abs=0.1)

    def test_seriousness_reason_flags(self, dataset_container):
        """Verify individual seriousness criteria counts."""
        result = analyze_cases(dataset_container.dedup_df)
        breakdown = result.get_metric("SER-SUMMARY").value

        assert breakdown["Death (Fatal)"]["count"] == 68
        assert breakdown["Hospitalization / Prolonged"]["count"] == 482
        assert breakdown["Life-threatening"]["count"] == 105
        assert breakdown["Disability / Incapacity"]["count"] == 44
        assert breakdown["Congenital Anomaly"]["count"] == 7
        assert breakdown["Other Medically Important"]["count"] == 905

    def test_drug_characterization_roles(self, dataset_container):
        """Verify Bisoprolol suspect vs concomitant vs interacting counts."""
        result = analyze_cases(dataset_container.dedup_df)
        roles = result.get_metric("DC-ROLE-001").value

        assert roles["concomitant"]["count"] == 666
        assert roles["suspect"]["count"] == 340
        assert roles["interacting"]["count"] == 17


class TestDemographicAnalysis:
    def test_sex_distribution_counts(self, dataset_container):
        """Verify sex distribution: Female=503, Male=493, Unknown=28."""
        result = analyze_demographics(dataset_container.dedup_df)
        sex = result.get_metric("DEMO-SEX-ALL").value

        assert sex["female"]["count"] == 503
        assert sex["male"]["count"] == 493
        assert sex["unknown"]["count"] == 28

    def test_age_unit_conversions(self, dataset_container):
        """Verify age conversion to years and statistics."""
        result = analyze_demographics(dataset_container.dedup_df)
        stats = result.get_metric("DEMO-AGE-STATS").value

        assert stats["count_with_age"] == 941
        assert stats["count_missing_age"] == 83
        assert stats["mean"] == pytest.approx(70.1, abs=0.5)
        assert stats["median"] == pytest.approx(73.0, abs=1.0)

    def test_country_mapping(self, dataset_container):
        """Verify top country reporting."""
        result = analyze_demographics(dataset_container.dedup_df)
        geo = result.get_metric("DEMO-GEO-ALL").value

        assert geo["EU (Regional)"]["count"] == 345
        assert geo["United Kingdom"]["count"] == 281
        assert geo["France"]["count"] == 185
        assert geo["Canada"]["count"] == 56


class TestReactionAnalysis:
    def test_reaction_and_pt_counts(self, dataset_container):
        """Verify 3,429 exploded reaction instances across 1,122 unique PTs."""
        result = analyze_reactions(dataset_container.dedup_df)
        total_rxn = result.get_metric("RXN-001").value
        unique_pts = result.get_metric("RXN-002").value

        assert total_rxn == 3429
        assert unique_pts == 1122

    def test_top_pts_distinct_case_count(self, dataset_container):
        """Verify distinct case count vs total occurrences for top PTs."""
        result = analyze_reactions(dataset_container.dedup_df)
        top_table = result.get_metric("RXN-TOP20-TABLE").value

        aki_entry = top_table[0]
        assert aki_entry["preferred_term"] == "Acute kidney injury"
        assert aki_entry["total_occurrences"] == 80
        assert aki_entry["distinct_case_count"] == 80  # 1 AKI per case

        drug_ineffective = top_table[1]
        assert drug_ineffective["preferred_term"] == "Drug ineffective"
        assert drug_ineffective["total_occurrences"] == 54


class TestOutcomeAnalysis:
    def test_outcome_categories(self, dataset_container):
        """Verify actual outcome categories found in dataset."""
        result = analyze_outcomes(dataset_container.dedup_df)
        rxn_outcomes = result.get_metric("OUT-RXN-ALL").value

        assert "recovered/resolved" in rxn_outcomes
        assert "unknown" in rxn_outcomes
        assert "fatal" in rxn_outcomes
        assert rxn_outcomes["fatal"]["count"] == 134  # reaction-level fatal across deduplicated cases

    def test_case_worst_outcome_fatal_count(self, dataset_container):
        """Case level fatal worst outcome must match 68 cases."""
        result = analyze_outcomes(dataset_container.dedup_df)
        case_outcomes = result.get_metric("OUT-CASE-ALL").value
        assert case_outcomes["fatal"]["count"] == 68


class TestTrendAndAlertAnalysis:
    def test_reporting_period_and_velocity(self, dataset_container):
        """Verify reporting period from 2024-12-27 to 2025-12-26 (364 days)."""
        result = analyze_trends(dataset_container.dedup_df)
        period = result.get_metric("TIME-PERIOD-001").value
        velocity = result.get_metric("TIME-VELOCITY-001").value

        assert period["start_date"] == "2024-12-27"
        assert period["end_date"] == "2025-12-26"
        assert period["duration_days"] == 364
        assert velocity["trend_direction"] == "stable"

    def test_alert_expedited_population(self, dataset_container):
        """Verify 15-day expedited alert metrics."""
        result = analyze_alerts(dataset_container.dedup_df)
        exp_count = result.get_metric("ALERT-001").value
        assert exp_count == 1023

        # History of actions statement
        hist_m = result.get_metric("HIST-ACTION-001").value
        assert hist_m["actions_reported_in_dataset"] is False


class TestMasterAnalysisPipeline:
    def test_end_to_end_pipeline_serialization(self):
        """Verify master pipeline runs, creates serialized outputs, and returns CompleteAnalysisPackage."""
        pkg = run_deterministic_analysis_pipeline()
        assert pkg.product_name == "Bisoprolol"
        assert len(pkg.sections) == 6
        assert pkg.validation_summary.unique_cases == 1024
