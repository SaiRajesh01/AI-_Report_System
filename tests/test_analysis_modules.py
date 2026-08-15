"""
Tests for canonical deterministic analysis modules.

Verifies that computed figures match exact analytical ground truth.
"""
import pytest
import pandas as pd

from src.data_loader import load_dataset_pipeline
from src.case_analysis import analyze_case_overview
from src.demographic_analysis import analyze_demographics
from src.reaction_analysis import analyze_reactions
from src.outcome_analysis import analyze_outcomes
from src.trend_analysis import analyze_trends
from src.alert_analysis import analyze_alerts
from src.config import DATASET_PATH


@pytest.fixture(scope="module")
def df_cases():
    """Load and deduplicate the dataset once for all tests."""
    container = load_dataset_pipeline(DATASET_PATH)
    return container.dedup_df


class TestCaseOverview:
    def test_total_cases(self, df_cases):
        res = analyze_case_overview(df_cases)
        assert res.get_metric("CO-001").value == 1024

    def test_serious_cases(self, df_cases):
        res = analyze_case_overview(df_cases)
        assert res.get_metric("CO-002").value == 1023

    def test_non_serious_cases(self, df_cases):
        res = analyze_case_overview(df_cases)
        assert res.get_metric("CO-004").value == 1

    def test_serious_pct(self, df_cases):
        res = analyze_case_overview(df_cases)
        assert res.get_metric("CO-003").value == 99.9

    def test_expedited_cases(self, df_cases):
        res = analyze_alerts(df_cases)
        assert res.get_metric("ALERT-001").value == 1023

    def test_reporting_period(self, df_cases):
        res = analyze_trends(df_cases)
        p = res.get_metric("TIME-PERIOD-001").value
        assert p["start_date"] == "2024-12-27"
        assert p["end_date"] == "2025-12-26"


class TestDemographics:
    def test_sex_distribution(self, df_cases):
        res = analyze_demographics(df_cases)
        sex = res.get_metric("DEMO-SEX-ALL").value
        assert sex["female"]["count"] == 503
        assert sex["male"]["count"] == 493

    def test_age_statistics(self, df_cases):
        res = analyze_demographics(df_cases)
        stats = res.get_metric("DEMO-AGE-STATS").value
        assert stats["mean"] == 70.05
        assert stats["median"] == 73.0

    def test_country_count(self, df_cases):
        res = analyze_demographics(df_cases)
        geo = res.get_metric("DEMO-GEO-ALL").value
        assert len(geo) >= 20


class TestReactions:
    def test_total_reactions(self, df_cases):
        res = analyze_reactions(df_cases)
        assert res.get_metric("RXN-001").value == 3429

    def test_unique_pts(self, df_cases):
        res = analyze_reactions(df_cases)
        assert res.get_metric("RXN-002").value == 1122

    def test_top_pt_is_aki(self, df_cases):
        res = analyze_reactions(df_cases)
        top_table = res.get_metric("RXN-TOP20-TABLE").value
        assert top_table[0]["preferred_term"] == "Acute kidney injury"
        assert top_table[0]["total_occurrences"] == 80
        assert top_table[0]["distinct_case_count"] == 80


class TestSeriousness:
    def test_fatal_cases(self, df_cases):
        res = analyze_case_overview(df_cases)
        crit = res.get_metric("SER-SUMMARY").value
        assert crit["Death (Fatal)"]["count"] == 68

    def test_hospitalization(self, df_cases):
        res = analyze_case_overview(df_cases)
        crit = res.get_metric("SER-SUMMARY").value
        assert crit["Hospitalization / Prolonged"]["count"] == 482


class TestOutcomes:
    def test_reaction_level_fatal(self, df_cases):
        res = analyze_outcomes(df_cases)
        fatal = res.get_metric("OUT-RXN-ALL").value.get("fatal", {}).get("count", 0)
        assert fatal > 0

    def test_case_level_total(self, df_cases):
        res = analyze_outcomes(df_cases)
        case_out = res.get_metric("OUT-CASE-ALL").value
        total = sum(v["count"] for v in case_out.values())
        assert total == 1024


class TestTemporal:
    def test_monthly_counts_exist(self, df_cases):
        res = analyze_trends(df_cases)
        monthly = res.get_metric("TIME-MONTHLY-COUNTS").value
        assert len(monthly) >= 12

    def test_trend_direction(self, df_cases):
        res = analyze_trends(df_cases)
        vel = res.get_metric("TIME-VELOCITY-001").value
        assert vel["trend_direction"] in ("stable", "increasing", "decreasing")


class TestDrugCharacterization:
    def test_bisoprolol_roles(self, df_cases):
        res = analyze_case_overview(df_cases)
        roles = res.get_metric("DC-ROLE-001").value
        assert roles["suspect"]["count"] == 340
        assert roles["concomitant"]["count"] == 666
        assert roles["interacting"]["count"] == 17
