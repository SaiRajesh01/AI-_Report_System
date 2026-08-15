"""
Unit and Integration Tests for Phase 5 Hardening, Evaluation Strategy, and Generalization.

Tests:
1. Data correctness (cases, seriousness, reactions, demographics, dates, trends, alerts).
2. Evidence provenance correctness (evidence_id, definition, source_fields, scope).
3. Context engineering and prompt isolation (no section cross-contamination).
4. Grounding verification (adversarial test cases with correct and injected false claims).
5. Report completeness across all 8 required sections.
6. Human-review decision gating logic.
7. Pipeline regression and deterministic reproducibility.
8. Evaluation harness benchmark calculation.
"""
from __future__ import annotations

import pytest
import pandas as pd

from src.data_loader import load_dataset_pipeline
from src.analysis_pipeline import run_deterministic_analysis_pipeline
from src.evidence_builder import build_all_section_evidence_packets, build_section_evidence_packet
from src.generation_models import SectionEvidencePacket, GroundedClaim
from src.grounding_validator import validate_generated_section
from src.llm_generator import generate_section_llm
from src.report_assembler import assemble_draft_pader_report
from src.review_manager import HumanReviewSession
from src.evaluator import ReportEvaluator, EvaluationBenchmarkResult
from src.report_config import PADER_SPECIFICATION, REPORT_SPECIFICATIONS


@pytest.fixture(scope="session")
def deterministic_package():
    """Master CompleteAnalysisPackage generated from actual dataset."""
    return run_deterministic_analysis_pipeline("Bisoprolol_icsr_sample_1068rows.csv")


@pytest.fixture(scope="session")
def section_packets(deterministic_package):
    """Scoped evidence packets for all sections."""
    return build_all_section_evidence_packets(deterministic_package)


# ─── 1. DATA CORRECTNESS TESTS ───────────────────────────────────────────────

class TestDataCorrectness:
    def test_unique_case_count_exactness(self, deterministic_package):
        val = deterministic_package.validation_summary
        assert val.total_raw_rows == 1068
        assert val.unique_cases == 1024
        assert val.duplicate_rows_count == 44

    def test_seriousness_counts(self, deterministic_package):
        case_sec = deterministic_package.sections["case_analysis"]
        assert case_sec.get_metric("CO-001").value == 1024
        assert case_sec.get_metric("CO-002").value == 1023
        assert case_sec.get_metric("CO-004").value == 1
        assert case_sec.get_metric("CO-003").value == 99.9

    def test_reaction_aggregation_exactness(self, deterministic_package):
        rxn_sec = deterministic_package.sections["reaction_analysis"]
        assert rxn_sec.get_metric("RXN-001").value == 3429
        assert rxn_sec.get_metric("RXN-002").value == 1122
        top_table = rxn_sec.get_metric("RXN-TOP20-TABLE").value
        assert top_table[0]["preferred_term"] == "Acute kidney injury"
        assert top_table[0]["total_occurrences"] == 80
        assert top_table[0]["distinct_case_count"] == 80

    def test_demographic_aggregation_exactness(self, deterministic_package):
        demo_sec = deterministic_package.sections["demographic_analysis"]
        sex_counts = demo_sec.get_metric("DEMO-SEX-ALL").value
        assert sex_counts["female"]["count"] == 503
        assert sex_counts["male"]["count"] == 493
        assert sex_counts["unknown"]["count"] == 28

        age_stat = demo_sec.get_metric("DEMO-AGE-STATS").value
        assert age_stat["count_with_age"] == 941
        assert age_stat["count_missing_age"] == 83
        assert age_stat["mean"] == 70.05
        assert age_stat["median"] == 73.0

    def test_date_range_and_velocity(self, deterministic_package):
        p = deterministic_package.reporting_period
        assert p["start_date"] == "2024-12-27"
        assert p["end_date"] == "2025-12-26"
        assert p["duration_days"] == 364

        trend_sec = deterministic_package.sections["trend_analysis"]
        vel = trend_sec.get_metric("TIME-VELOCITY-001").value
        assert vel["first_half_cases"] == 511
        assert vel["second_half_cases"] == 513

    def test_alert_calculations(self, deterministic_package):
        alert_sec = deterministic_package.sections["alert_analysis"]
        assert alert_sec.get_metric("ALERT-001").value == 1023


# ─── 2. EVIDENCE PROVENANCE TESTS ────────────────────────────────────────────

class TestEvidenceProvenance:
    def test_all_metrics_have_required_provenance_fields(self, deterministic_package):
        """Every single metric must contain evidence_id, definition, scope, and source_fields."""
        for sec_name, sec_obj in deterministic_package.sections.items():
            for m in sec_obj.metrics:
                assert m.evidence_id is not None and len(m.evidence_id) > 0, f"Missing evidence_id in {sec_name}"
                assert m.metric_name is not None and len(m.metric_name) > 0
                assert m.calculation_definition is not None and len(m.calculation_definition) > 0
                assert len(m.source_fields) > 0, f"Missing source_fields in {m.evidence_id}"
                assert m.scope in ("case-level", "reaction-level", "aggregate", "dataset-level")


# ─── 3. CONTEXT ENGINEERING & PROMPT ISOLATION ────────────────────────────────

class TestContextIsolation:
    def test_sections_receive_only_approved_evidence(self, section_packets):
        """Verify strict evidence isolation: reactions section does not receive demographics."""
        rxn_packet = section_packets["reaction_analysis"]
        assert "total_reaction_occurrences" in rxn_packet.approved_metrics
        assert "sex_distribution_breakdown" not in rxn_packet.approved_metrics

        history_packet = section_packets["history_of_actions"]
        assert "total_reaction_occurrences" not in history_packet.approved_metrics
        assert "history_of_actions_status" in history_packet.approved_metrics


# ─── 4. ADVERSARIAL GROUNDING TESTS ──────────────────────────────────────────

class TestAdversarialGrounding:
    def test_correct_case_count_passes(self, section_packets):
        packet = section_packets["narrative_summary"]
        text = "A total of 1,024 cases were received for Bisoprolol during the period, with 1,023 serious cases."
        out = validate_generated_section("narrative_summary", text, packet)
        assert out.grounding_score == 1.0

    def test_incorrect_case_count_is_flagged(self, section_packets):
        packet = section_packets["narrative_summary"]
        text = "A total of 5,432 cases were received for Bisoprolol, with 4,000 deaths."
        out = validate_generated_section("narrative_summary", text, packet)
        flagged = [c for c in out.claims if c.status == "FLAGGED"]
        assert len(flagged) > 0
        assert any("5,432" in c.claim_text or "5432" in str(c.extracted_figures) for c in flagged)

    def test_unsupported_causal_claim_is_flagged(self, section_packets):
        packet = section_packets["trends"]
        text = "The data confirms a causal relationship between Bisoprolol and severe renal failure."
        out = validate_generated_section("trends", text, packet)
        flagged = [c for c in out.claims if c.status == "FLAGGED"]
        assert len(flagged) > 0
        assert any("causal" in c.flag_reason.lower() for c in flagged)

    def test_unsupported_regulatory_action_is_flagged(self, section_packets):
        packet = section_packets["history_of_actions"]
        text = "During the interval, the product labeling was updated to add a black box warning."
        out = validate_generated_section("history_of_actions", text, packet)
        flagged = [c for c in out.claims if c.status == "FLAGGED"]
        assert len(flagged) > 0
        assert any("action" in c.flag_reason.lower() for c in flagged)

    def test_unsupported_soc_claim_is_flagged(self, section_packets):
        packet = section_packets["reaction_analysis"]
        text = "Adverse events were classified under the Cardiac disorders SOC."
        out = validate_generated_section("reaction_analysis", text, packet)
        flagged = [c for c in out.claims if c.status == "FLAGGED"]
        assert len(flagged) > 0


# ─── 5. REPORT COMPLETENESS TESTS ────────────────────────────────────────────

class TestReportCompleteness:
    def test_all_eight_sections_produced(self, section_packets):
        sections = {sid: generate_section_llm(sid, pkt) for sid, pkt in section_packets.items()}
        period = {"start_date": "2024-12-27", "end_date": "2025-12-26", "duration_days": 364}
        report = assemble_draft_pader_report(sections, period, "completeness_test.md")

        assert len(report.sections) == 8
        for sid in section_packets:
            assert sid in report.sections
            assert len(report.sections[sid].generated_text) > 50


# ─── 6. HUMAN REVIEW LOGIC TESTS ─────────────────────────────────────────────

class TestHumanReviewLogic:
    def test_flagged_sections_prevent_clean_approval(self, tmp_path):
        session = HumanReviewSession(session_file=tmp_path / "review_test.json")
        session.init_sections([{"id": "sec_1", "title": "Section 1"}])
        session.record_decision("sec_1", "Section 1", "flag", comment="Requires revision")
        assert not session.is_all_approved()

    def test_approved_sections_allow_finalization(self, tmp_path):
        session = HumanReviewSession(session_file=tmp_path / "review_test2.json")
        session.init_sections([{"id": "sec_1", "title": "Section 1"}])
        session.record_decision("sec_1", "Section 1", "approve", comment="Looks great")
        assert session.is_all_approved()

    def test_regeneration_replaces_draft_correctly(self, section_packets):
        pkt = section_packets["trends"]
        sec_v1 = generate_section_llm("trends", pkt)
        sec_v2 = generate_section_llm("trends", pkt)
        assert sec_v2.section_name == sec_v1.section_name
        assert len(sec_v2.generated_text) > 50


# ─── 7. DETERMINISTIC REGRESSION TESTS ───────────────────────────────────────

class TestDeterministicRegression:
    def test_repeated_runs_produce_identical_metrics(self):
        """Verify 100% reproducible deterministic analytics across multiple executions."""
        pkg1 = run_deterministic_analysis_pipeline()
        pkg2 = run_deterministic_analysis_pipeline()

        assert pkg1.validation_summary.unique_cases == pkg2.validation_summary.unique_cases == 1024
        assert (
            pkg1.sections["case_analysis"].get_metric("CO-002").value ==
            pkg2.sections["case_analysis"].get_metric("CO-002").value == 1023
        )
        assert (
            pkg1.sections["reaction_analysis"].get_metric("RXN-001").value ==
            pkg2.sections["reaction_analysis"].get_metric("RXN-001").value == 3429
        )


# ─── 8. EVALUATION HARNESS BENCHMARK TESTS ───────────────────────────────────

class TestEvaluationHarness:
    def test_evaluator_runs_and_produces_valid_benchmark(self, deterministic_package, section_packets):
        sections = {sid: generate_section_llm(sid, pkt) for sid, pkt in section_packets.items()}
        evaluator = ReportEvaluator(package=deterministic_package)
        result: EvaluationBenchmarkResult = evaluator.evaluate_generated_report(sections, run_id="test-run-100")

        assert result.section_completeness_rate == 1.0
        assert result.numerical_precision >= 0.85
        assert result.unsupported_claim_rate <= 0.15
        assert result.deterministic_consistency_score == 1.0
        assert result.regeneration_success_rate == 1.0
        assert result.passed_all_thresholds is True


# ─── 9. REPORT SPECIFICATION GENERALIZATION TESTS ─────────────────────────────

class TestReportGeneralizationConfig:
    def test_pader_specification_structure(self):
        assert PADER_SPECIFICATION.report_type == "PADER"
        assert len(PADER_SPECIFICATION.sections) == 8
        deps = PADER_SPECIFICATION.get_analysis_dependencies()
        assert "case_analysis" in deps
        assert "reaction_analysis" in deps
        assert "trend_analysis" in deps
