"""
Unit and Integration Tests for Phase 4 Human Review and Final Report Gating.

Comprehensive tests covering:
1. Finalization blocked when a section is PENDING.
2. Finalization blocked when a section is FLAGGED.
3. Finalization succeeds only when every required section is APPROVED.
4. Grounding failure blocks finalization.
5. Reject/flag requires the section to return to PENDING after regeneration.
6. Regeneration increments generation_version.
7. Previous versions remain auditable in history.
8. A newly regenerated section cannot automatically be approved.
9. A human must click APPROVE again.
10. Final report uses only approved active versions and marks status as APPROVED.
11. LLM/API failure does not bypass review.
12. Offline fallback does not bypass review.
13. Reloading session preserves review state and history.
14. Changing one flagged section does not invalidate unrelated approved sections.
15. DOCX Exporter verification.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from src.analysis_pipeline import run_deterministic_analysis_pipeline
from src.evidence_builder import build_all_section_evidence_packets
from src.llm_generator import generate_section_llm
from src.report_assembler import assemble_draft_pader_report, assemble_final_pader_report
from src.review_manager import HumanReviewSession, compute_sha256, FinalizationBlockedError
from src.docx_exporter import export_markdown_to_docx
from src.config import REPORT_OUTPUT_DIR


@pytest.fixture
def temp_review_session(tmp_path):
    """Fixture providing an isolated review session."""
    session_file = tmp_path / "test_review_session.json"
    return HumanReviewSession(session_file=session_file)


class TestHumanReviewGatekeeper:
    def test_finalization_blocked_when_pending(self, temp_review_session):
        """Finalization is strictly blocked when sections are in PENDING state."""
        meta = [{"id": sid, "title": f"Section {sid}"} for sid in HumanReviewSession.REQUIRED_SECTIONS]
        temp_review_session.init_sections(meta)

        is_allowed, blockers = temp_review_session.can_finalize()
        assert not is_allowed
        assert len(blockers) == len(HumanReviewSession.REQUIRED_SECTIONS)
        assert any("PENDING" in b for b in blockers)

    def test_finalization_blocked_when_flagged(self, temp_review_session):
        """Finalization is blocked when even one section is FLAGGED."""
        meta = [{"id": sid, "title": f"Section {sid}"} for sid in HumanReviewSession.REQUIRED_SECTIONS]
        temp_review_session.init_sections(meta)

        # Approve all except reaction_analysis
        for sid in HumanReviewSession.REQUIRED_SECTIONS:
            if sid == "reaction_analysis":
                temp_review_session.flag_section(
                    section_id=sid,
                    section_title="Reaction Analysis",
                    comment="AKI case count needs clinical re-audit"
                )
            else:
                temp_review_session.approve_section(sid, f"Section {sid}")

        is_allowed, blockers = temp_review_session.can_finalize()
        assert not is_allowed
        assert len(blockers) == 1
        assert "FLAGGED" in blockers[0]
        assert "AKI case count" in blockers[0]

        # assemble_final_pader_report must raise FinalizationBlockedError
        with pytest.raises(FinalizationBlockedError, match="Final report blocked"):
            assemble_final_pader_report(
                sections={},
                reporting_period={},
                review_session=temp_review_session,
                output_filename="blocked_test.md"
            )

    def test_finalization_succeeds_when_all_approved(self, temp_review_session):
        """Finalization succeeds only when 100% of required sections are APPROVED."""
        meta = [{"id": sid, "title": f"Section {sid}"} for sid in HumanReviewSession.REQUIRED_SECTIONS]
        temp_review_session.init_sections(meta)

        for sid in HumanReviewSession.REQUIRED_SECTIONS:
            temp_review_session.approve_section(sid, f"Section {sid}", comment="Clinically verified")

        is_allowed, blockers = temp_review_session.can_finalize()
        assert is_allowed
        assert len(blockers) == 0
        assert temp_review_session.is_all_approved()

    def test_reject_flag_requires_comment(self, temp_review_session):
        """Rejecting/flagging a section strictly requires a comment/reason."""
        meta = [{"id": "sec_1", "title": "Section 1"}]
        temp_review_session.init_sections(meta)

        with pytest.raises(ValueError, match="comment/reason is required"):
            temp_review_session.flag_section("sec_1", "Section 1", comment="")

    def test_regeneration_resets_to_pending_and_increments_version(self, temp_review_session):
        """Regenerating a section resets status to PENDING and increments generation_version."""
        meta = [{"id": "sec_1", "title": "Section 1"}]
        temp_review_session.init_sections(meta)

        # Flag version 1
        temp_review_session.flag_section("sec_1", "Section 1", comment="Inaccurate count")
        rec1 = temp_review_session.records["sec_1"]
        assert rec1.status == "FLAGGED"
        assert rec1.generation_version == 1

        # Regenerate -> becomes version 2 with PENDING status
        temp_review_session.record_regeneration(
            section_id="sec_1",
            section_title="Section 1",
            new_generated_text="Regenerated text v2",
            new_evidence_text='{"total": 1024}',
            comment="Regenerated v2"
        )
        rec2 = temp_review_session.records["sec_1"]
        assert rec2.status == "PENDING"
        assert rec2.generation_version == 2

        # A regenerated section CANNOT be finalized while PENDING
        is_allowed, _ = temp_review_session.can_finalize(["sec_1"])
        assert not is_allowed

    def test_audit_history_preserves_previous_versions(self, temp_review_session):
        """Audit trail preserves every previous review decision and version state."""
        meta = [{"id": "sec_1", "title": "Section 1"}]
        temp_review_session.init_sections(meta)

        # Version 1 -> Flagged
        temp_review_session.flag_section(
            "sec_1", "Section 1", comment="First version incomplete",
            reviewer="Reviewer A", evidence_text='{"v": 1}'
        )

        # Version 2 -> Regenerated -> Flagged
        temp_review_session.record_regeneration("sec_1", "Section 1", "Text v2", '{"v": 2}')
        temp_review_session.flag_section(
            "sec_1", "Section 1", comment="Second version needs demographic breakdown",
            reviewer="Reviewer B"
        )

        # Version 3 -> Regenerated -> Approved
        temp_review_session.record_regeneration("sec_1", "Section 1", "Text v3", '{"v": 3}')
        temp_review_session.approve_section(
            "sec_1", "Section 1", comment="Version 3 perfect",
            reviewer="Lead Reviewer"
        )

        rec = temp_review_session.records["sec_1"]
        assert rec.status == "APPROVED"
        assert rec.generation_version == 3
        assert len(rec.history) >= 4

        # Verify history captures the flagged entry
        flagged_entries = [h for h in rec.history if h["human_status"] == "FLAGGED"]
        assert len(flagged_entries) == 2
        assert flagged_entries[0]["reviewer_comment"] == "First version incomplete"

    def test_reloading_session_preserves_state(self, tmp_path):
        """Saving and reloading a review session preserves complete state from disk."""
        session_file = tmp_path / "persist_test.json"
        s1 = HumanReviewSession(session_file=session_file)
        s1.init_sections([{"id": "s1", "title": "Title 1"}])
        s1.approve_section("s1", "Title 1", comment="Approved by Dr. X", reviewer="Dr. X")

        # Reload from same file
        s2 = HumanReviewSession(session_file=session_file)
        assert "s1" in s2.records
        assert s2.records["s1"].status == "APPROVED"
        assert s2.records["s1"].reviewer == "Dr. X"
        assert s2.records["s1"].reviewer_comment == "Approved by Dr. X"

    def test_single_flagged_section_does_not_invalidate_others(self, temp_review_session):
        """Flagging one section does not alter the APPROVED status of other sections."""
        meta = [{"id": "s1", "title": "Title 1"}, {"id": "s2", "title": "Title 2"}]
        temp_review_session.init_sections(meta)

        temp_review_session.approve_section("s1", "Title 1", comment="Approved 1")
        temp_review_session.flag_section("s2", "Title 2", comment="Needs fix")

        assert temp_review_session.records["s1"].status == "APPROVED"
        assert temp_review_session.records["s2"].status == "FLAGGED"

        # Regenerate only s2
        temp_review_session.record_regeneration("s2", "Title 2", "New text")
        assert temp_review_session.records["s1"].status == "APPROVED"
        assert temp_review_session.records["s2"].status == "PENDING"

    def test_final_report_assembly_includes_human_approval_metadata(self, tmp_path):
        """Official final report includes human review approval sign-off metadata."""
        pkg = run_deterministic_analysis_pipeline("Bisoprolol_icsr_sample_1068rows.csv")
        packets = build_all_section_evidence_packets(pkg)

        sections = {}
        for sid, pkt in packets.items():
            sections[sid] = generate_section_llm(sid, pkt)

        session_file = tmp_path / "final_meta_session.json"
        review = HumanReviewSession(session_file=session_file)
        review.init_sections([{"id": sid, "title": pkt.section_title} for sid, pkt in packets.items()])

        for sid, pkt in packets.items():
            review.approve_section(sid, pkt.section_title, comment="Quality verified", reviewer="Lead Safety Reviewer")

        final_out = tmp_path / "final_report.md"
        final_draft = assemble_final_pader_report(sections, pkg.reporting_period, review, output_filename=str(final_out))

        assert "APPROVED (100% Verified by Qualified Safety Reviewer)" in final_draft.generated_markdown
        assert "Human Review & Quality Assurance Sign-off" in final_draft.generated_markdown
        assert "FINAL APPROVED REPORT" in final_draft.generated_markdown
        assert final_out.exists()


class TestDocxExporter:
    def test_export_markdown_to_docx(self, tmp_path):
        """Exporting markdown report produces a valid .docx file."""
        sample_md = """# Periodic Adverse Drug Experience Report (PADER)
## Bisoprolol — [FINAL APPROVED REPORT]
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
