"""
Unit and Integration Tests for Phase 4 Human Review and UI Components.

Tests:
1. HumanReviewSession state lifecycle (init, approve, flag, regenerate, audit logging).
2. Approval gating logic for final report assembly.
3. Cryptographic evidence and generated text hashing.
4. DOCX Exporter verification.
5. Complete end-to-end review workflow: Generate -> Review -> Flag -> Regenerate -> Approve -> Final Report.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from src.analysis_pipeline import run_deterministic_analysis_pipeline
from src.evidence_builder import build_all_section_evidence_packets
from src.llm_generator import generate_section_llm
from src.report_assembler import assemble_draft_pader_report
from src.review_manager import HumanReviewSession, compute_sha256
from src.docx_exporter import export_markdown_to_docx
from src.config import REPORT_OUTPUT_DIR


@pytest.fixture
def temp_review_session(tmp_path):
    """Fixture providing an isolated review session."""
    session_file = tmp_path / "test_review_session.json"
    return HumanReviewSession(session_file=session_file)


class TestHumanReviewSession:
    def test_init_sections(self, temp_review_session):
        """Sections should initialize in PENDING state."""
        meta = [
            {"id": "sec_1", "title": "1. Section One"},
            {"id": "sec_2", "title": "2. Section Two"}
        ]
        temp_review_session.init_sections(meta)
        assert len(temp_review_session.records) == 2
        assert temp_review_session.records["sec_1"].status == "PENDING"
        assert not temp_review_session.is_all_approved()

    def test_approve_section(self, temp_review_session):
        """Approving a section sets status to APPROVED and stores evidence hash."""
        meta = [{"id": "sec_1", "title": "1. Section One"}]
        temp_review_session.init_sections(meta)

        temp_review_session.record_decision(
            section_id="sec_1",
            section_title="1. Section One",
            decision="approve",
            comment="Clinically accurate",
            reviewer="Dr. Jane Smith",
            evidence_text='{"total_cases": 1024}',
            generated_text="1,024 cases were received."
        )

        rec = temp_review_session.records["sec_1"]
        assert rec.status == "APPROVED"
        assert rec.reviewer_comment == "Clinically accurate"
        assert len(rec.evidence_hash) > 0
        assert temp_review_session.is_all_approved()

    def test_flag_section_is_non_destructive(self, temp_review_session):
        """Flagging a section updates status without deleting text and retains reason."""
        meta = [{"id": "sec_1", "title": "1. Section One"}]
        temp_review_session.init_sections(meta)

        temp_review_session.record_decision(
            section_id="sec_1",
            section_title="1. Section One",
            decision="flag",
            comment="Need demographic sub-breakdown",
            reviewer="Dr. Reviewer",
            evidence_text='{}',
            generated_text="Preliminary text"
        )

        assert not temp_review_session.is_all_approved()
        flagged = temp_review_session.get_flagged_sections()
        assert len(flagged) == 1
        assert flagged[0].reviewer_comment == "Need demographic sub-breakdown"

    def test_regeneration_increments_version(self, temp_review_session):
        """Regenerating a section resets status to PENDING and logs version."""
        meta = [{"id": "sec_1", "title": "1. Section One"}]
        temp_review_session.init_sections(meta)

        temp_review_session.record_decision(
            section_id="sec_1",
            section_title="1. Section One",
            decision="regenerate",
            comment="Regenerated version 2",
            generation_version=2
        )

        rec = temp_review_session.records["sec_1"]
        assert rec.status == "PENDING"
        assert rec.generation_version == 2


class TestDocxExporter:
    def test_export_markdown_to_docx(self, tmp_path):
        """Exporting markdown report produces a valid .docx file."""
        sample_md = """# Periodic Adverse Drug Experience Report (PADER)
## Bisoprolol
**Reporting Period**: 2024-12-27 to 2025-12-26

## 1. Summary Analysis of Cases

| Metric | Value |
|---|---|
| Total Cases | 1024 |
| Serious Cases | 1023 |

- Key finding: High seriousness percentage.
"""
        docx_file = tmp_path / "test_report.docx"
        out_path = export_markdown_to_docx(sample_md, docx_file)
        assert out_path.exists()
        assert out_path.stat().st_size > 1000


class TestEndToEndWorkflow:
    def test_complete_review_workflow(self, tmp_path):
        """
        Verify the complete workflow:
        Raw data -> Deterministic analysis -> Evidence packets -> Generated sections ->
        Review -> Flag -> Regenerate -> Approve -> Final Report.
        """
        # 1. Deterministic analysis & evidence packets
        pkg = run_deterministic_analysis_pipeline("Bisoprolol_icsr_sample_1068rows.csv")
        packets = build_all_section_evidence_packets(pkg)

        # 2. Section generation
        sections = {}
        for sid, pkt in packets.items():
            sections[sid] = generate_section_llm(sid, pkt)

        # 3. Initialize review session
        session_file = tmp_path / "e2e_review_session.json"
        review = HumanReviewSession(session_file=session_file)
        review.init_sections([{"id": sid, "title": pkt.section_title} for sid, pkt in packets.items()])

        # 4. Reviewer flags narrative_summary
        review.record_decision(
            section_id="narrative_summary",
            section_title=packets["narrative_summary"].section_title,
            decision="flag",
            comment="Clarify concomitant usage"
        )
        assert not review.is_all_approved()

        # 5. Regenerate narrative_summary
        new_sec = generate_section_llm("narrative_summary", packets["narrative_summary"])
        sections["narrative_summary"] = new_sec
        review.record_decision(
            section_id="narrative_summary",
            section_title=packets["narrative_summary"].section_title,
            decision="regenerate",
            generation_version=2
        )

        # 6. Approve all sections
        for sid, pkt in packets.items():
            review.record_decision(
                section_id=sid,
                section_title=pkt.section_title,
                decision="approve",
                comment="Approved"
            )

        assert review.is_all_approved()

        # 7. Final Report Assembly and DOCX export
        final_report = assemble_draft_pader_report(sections, pkg.reporting_period, "final_pader_test.md")
        docx_out = tmp_path / "final_pader_test.docx"
        export_markdown_to_docx(final_report.generated_markdown, docx_out)

        assert final_report.overall_grounding_score >= 0.9
        assert docx_out.exists()
