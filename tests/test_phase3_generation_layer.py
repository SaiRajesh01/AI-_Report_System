"""
Unit and Integration Tests for Phase 3 AI Reasoning and Generation Layer.

Tests:
1. Section-specific evidence packet scoping (no data dumping).
2. Prompt template formatting with constraints.
3. Grounding validator hallucination & constraint checks.
4. Single-section regeneration.
5. End-to-end draft report assembly.
"""
from __future__ import annotations

import pytest
import pandas as pd

from src.data_loader import load_dataset_pipeline
from src.analysis_pipeline import run_deterministic_analysis_pipeline
from src.evidence_builder import build_section_evidence_packet, build_all_section_evidence_packets
from src.grounding_validator import validate_generated_section, extract_all_numbers
from src.llm_generator import generate_section_llm, format_user_prompt
from src.report_assembler import assemble_draft_pader_report
from src.generation_models import SectionEvidencePacket, GroundedClaim


@pytest.fixture(scope="session")
def analysis_package():
    """Run Phase 2 deterministic analysis to obtain master evidence package."""
    return run_deterministic_analysis_pipeline("Bisoprolol_icsr_sample_1068rows.csv")


@pytest.fixture(scope="session")
def evidence_packets(analysis_package):
    """Build all section evidence packets."""
    return build_all_section_evidence_packets(analysis_package)


class TestEvidenceBuilder:
    def test_all_eight_sections_have_packets(self, evidence_packets):
        """All 8 standard PADER sections must have scoped evidence packets."""
        expected_sections = {
            "reporting_period", "narrative_summary", "case_summary",
            "reaction_analysis", "serious_cases", "trends",
            "history_of_actions", "case_listing"
        }
        assert set(evidence_packets.keys()) == expected_sections

    def test_evidence_scoping_isolation(self, evidence_packets):
        """Sections must only receive relevant metrics (e.g. reaction_analysis does not get demographics)."""
        rxn_packet = evidence_packets["reaction_analysis"]
        assert "total_reaction_occurrences" in rxn_packet.approved_metrics
        assert "sex_distribution_breakdown" not in rxn_packet.approved_metrics

        demo_packet = evidence_packets["case_summary"]
        assert "sex_distribution_breakdown" in demo_packet.approved_metrics
        assert "reporting_volume_velocity" not in demo_packet.approved_metrics

    def test_constraints_included_in_packets(self, evidence_packets):
        """Packets must contain explicit constraints regarding SOC, arithmetic, and tone."""
        rxn_packet = evidence_packets["reaction_analysis"]
        constraints_str = " ".join(rxn_packet.constraints).lower()
        assert "soc" in constraints_str
        assert "arithmetic" in constraints_str


class TestPromptArchitecture:
    def test_prompt_formatting(self, evidence_packets):
        """Prompts must inject evidence JSON cleanly without leaving unreplaced placeholders."""
        packet = evidence_packets["narrative_summary"]
        formatted = format_user_prompt("narrative_summary", packet)
        assert "{evidence_json}" not in formatted
        assert "approved_metrics" in formatted
        assert "Bisoprolol" in formatted


class TestGroundingValidator:
    def test_valid_grounded_text_passes(self, evidence_packets):
        """Text containing only approved metrics should achieve high grounding score."""
        packet = evidence_packets["narrative_summary"]
        text = "During the period, 1,024 unique cases were received for Bisoprolol, of which 1,023 (99.9%) were serious."
        out = validate_generated_section("narrative_summary", text, packet)
        assert out.grounding_score >= 0.9
        assert len([c for c in out.claims if c.status == "FLAGGED"]) == 0

    def test_ungrounded_numbers_are_flagged(self, evidence_packets):
        """Text with fabricated numbers must be detected and flagged."""
        packet = evidence_packets["narrative_summary"]
        fabricated_text = "A total of 9,999 cases were received, including 8,888 deaths."
        out = validate_generated_section("narrative_summary", fabricated_text, packet)
        assert len(out.warnings_or_uncertainties) > 0
        assert any("ungrounded" in w.lower() for w in out.warnings_or_uncertainties)
        flagged_claims = [c for c in out.claims if c.status == "FLAGGED"]
        assert len(flagged_claims) > 0

    def test_forbidden_soc_inference_is_flagged(self, evidence_packets):
        """Text asserting an unsupported System Organ Class grouping must be flagged."""
        packet = evidence_packets["reaction_analysis"]
        soc_text = "Reactions were categorized under the Blood and lymphatic system disorders SOC."
        out = validate_generated_section("reaction_analysis", soc_text, packet)
        assert any("soc" in w.lower() for w in out.warnings_or_uncertainties)
        flagged = [c for c in out.claims if c.status == "FLAGGED"]
        assert len(flagged) > 0

    def test_invented_actions_are_flagged(self, evidence_packets):
        """Text claiming an invented regulatory action must be flagged."""
        packet = evidence_packets["history_of_actions"]
        action_text = "The product labeling was updated to include a black box warning."
        out = validate_generated_section("history_of_actions", action_text, packet)
        assert any("action" in w.lower() for w in out.warnings_or_uncertainties)


class TestSingleSectionRegeneration:
    def test_regenerate_specific_section_independently(self, evidence_packets):
        """Must allow generating or regenerating an individual section in isolation."""
        trend_packet = evidence_packets["trends"]
        sec_out = generate_section_llm("trends", trend_packet)
        assert sec_out.section_name == "6. Trends and Important Observations"
        assert len(sec_out.generated_text) > 100
        assert sec_out.grounding_score > 0.8


class TestReportAssembly:
    def test_draft_report_assembly(self, evidence_packets):
        """Assembling all sections produces a CompleteDraftReport with grounding audit."""
        sections = {}
        for sid, packet in evidence_packets.items():
            sections[sid] = generate_section_llm(sid, packet)

        period = {"start_date": "2024-12-27", "end_date": "2025-12-26", "duration_days": 364}
        draft_report = assemble_draft_pader_report(sections, period, "test_draft_pader.md")

        assert draft_report.product_name == "Bisoprolol"
        assert len(draft_report.sections) == 8
        assert draft_report.overall_grounding_score >= 0.9
        assert "Claim-Level Grounding Audit" in draft_report.generated_markdown
