"""
Tests for canonical evidence packet assembly and validation.
"""
import pytest
import json
import pandas as pd

from src.data_loader import load_dataset_pipeline
from src.analysis_pipeline import run_deterministic_analysis_pipeline
from src.evidence_builder import build_all_section_evidence_packets
from src.generation_models import SectionEvidencePacket
from src.config import DATASET_PATH, PRODUCT_NAME


@pytest.fixture(scope="module")
def all_packets():
    """Build all evidence packets from the real dataset."""
    pkg = run_deterministic_analysis_pipeline(DATASET_PATH)
    container = load_dataset_pipeline(DATASET_PATH)
    return build_all_section_evidence_packets(pkg, dedup_df=container.dedup_df)


class TestEvidenceAssembly:
    def test_all_sections_have_packets(self, all_packets):
        """Every PADER section should have an evidence packet."""
        expected = {
            "reporting_period", "narrative_summary", "case_summary",
            "reaction_analysis", "serious_cases", "trends",
            "history_of_actions", "case_listing",
        }
        assert set(all_packets.keys()) == expected

    def test_narrative_summary_has_required_analyses(self, all_packets):
        """Narrative summary should have required approved metrics."""
        packet = all_packets["narrative_summary"]
        assert "total_unique_cases" in packet.approved_metrics
        assert "serious_cases_count" in packet.approved_metrics

    def test_history_of_actions_has_no_reactions(self, all_packets):
        """History of actions must be scoped and not contain reaction metrics."""
        packet = all_packets["history_of_actions"]
        assert "total_reaction_occurrences" not in packet.approved_metrics

    def test_packets_are_json_serializable(self, all_packets):
        """All packets should serialize to JSON without error."""
        for name, packet in all_packets.items():
            serialized = json.dumps(packet.model_dump(), default=str)
            assert len(serialized) > 0

    def test_product_name_in_all_packets(self, all_packets):
        """Every packet should have the product name."""
        for packet in all_packets.values():
            assert packet.product_name == PRODUCT_NAME

    def test_reporting_period_in_all_packets(self, all_packets):
        """Every packet should have reporting period dates."""
        for packet in all_packets.values():
            assert "start_date" in packet.reporting_period
            assert "end_date" in packet.reporting_period
