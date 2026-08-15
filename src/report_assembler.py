"""
Report Assembler: Combines validated section outputs into a complete,
DOCX-friendly PADER-style regulatory document.

Includes metadata headers, table of contents, rendered Markdown sections,
and a comprehensive Claim-Level Grounding Audit Appendix.

Enforces strict separation between DRAFT (unreviewed/pending) and FINAL (human-approved) documents.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import PRODUCT_NAME, APPLICATION_NUMBER, COMPANY_NAME, REPORT_OUTPUT_DIR
from src.generation_models import GeneratedSectionOutput, CompleteDraftReport
from src.review_manager import HumanReviewSession, FinalizationBlockedError


SECTION_ORDER = [
    "reporting_period",
    "narrative_summary",
    "case_summary",
    "reaction_analysis",
    "serious_cases",
    "trends",
    "history_of_actions",
    "case_listing",
]


def assemble_draft_pader_report(
    sections: dict[str, GeneratedSectionOutput],
    reporting_period: dict,
    output_filename: str = "pader_bisoprolol_draft.md"
) -> CompleteDraftReport:
    """
    Assemble generated sections into a DRAFT PADER report.
    Clearly marks document as DRAFT - PENDING HUMAN REVIEW.
    """
    parts: list[str] = []

    p_start = reporting_period.get("start_date", "2024-12-27")
    p_end = reporting_period.get("end_date", "2025-12-26")
    gen_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Header with Draft Warning
    parts.append("# Periodic Adverse Drug Experience Report (PADER)")
    parts.append(f"## {PRODUCT_NAME} — [DRAFT: PENDING HUMAN REVIEW]")
    parts.append(f"> **REGULATORY NOTICE**: This document is an unreviewed draft generated for human safety review. It has not been approved for regulatory submission.")
    parts.append("")
    parts.append(f"**Application Number**: {APPLICATION_NUMBER}")
    parts.append(f"**Marketing Authorization Holder**: {COMPANY_NAME}")
    parts.append(f"**Reporting Period**: {p_start} to {p_end} ({reporting_period.get('duration_days', 364)} days)")
    parts.append(f"**Regulatory Standard**: United States FDA 21 CFR 314.80")
    parts.append(f"**Draft Generated**: {gen_time}")
    parts.append("")

    # Table of Contents
    parts.append("---")
    parts.append("## Table of Contents")
    parts.append("")
    for sid in SECTION_ORDER:
        sec_out = sections.get(sid)
        if sec_out:
            flag_note = f" (Grounding: {sec_out.grounding_score:.0%})" if sec_out.grounding_score < 1.0 else ""
            parts.append(f"- [{sec_out.section_name}](#{sec_out.section_name.lower().replace(' ', '-').replace('/', '').replace('.', '')}){flag_note}")
    parts.append("- [Appendix: Claim-Level Grounding Audit](#appendix-claim-level-grounding-audit)")
    parts.append("")
    parts.append("---")
    parts.append("")

    # Section Content
    total_claims = 0
    flagged_claims = 0
    all_claims = []

    for sid in SECTION_ORDER:
        sec_out = sections.get(sid)
        if not sec_out:
            continue

        if sec_out.warnings_or_uncertainties:
            parts.append(f"> **Verification Note**: {len(sec_out.warnings_or_uncertainties)} audit observation(s) noted for this section.")
            for w in sec_out.warnings_or_uncertainties:
                parts.append(f"> * {w}")
            parts.append("")

        parts.append(sec_out.generated_text)
        parts.append("")
        parts.append("---")
        parts.append("")

        for c in sec_out.claims:
            total_claims += 1
            if c.status in ("FLAGGED", "UNSUPPORTED"):
                flagged_claims += 1
            all_claims.append((sec_out.section_name, c))

    # Appendix
    parts.append("## Appendix: Claim-Level Grounding Audit")
    parts.append("")
    parts.append("The following audit table verifies every factual statement against pre-computed deterministic evidence:\n")
    parts.append("| Section | Claim Statement | Evidence ID | Figures | Status | Notes |")
    parts.append("|---|---|---|---|---|---|")

    for sec_name, claim in all_claims:
        clean_text = claim.claim_text.replace("|", "\\|")[:90] + ("..." if len(claim.claim_text) > 90 else "")
        ev_id = claim.evidence_id or "N/A"
        figs = ", ".join(claim.extracted_figures[:4]) if claim.extracted_figures else "--"
        status_icon = "PASS [VERIFIED]" if claim.status == "VERIFIED" else f"WARN [{claim.status}]"
        notes = claim.flag_reason or "Grounded"
        parts.append(f"| {sec_name} | {clean_text} | {ev_id} | {figs} | {status_icon} | {notes} |")

    parts.append("")

    overall_grounding = round((total_claims - flagged_claims) / total_claims, 3) if total_claims > 0 else 1.0
    rendered_markdown = "\n".join(parts)

    out_dir = Path(REPORT_OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / output_filename
    out_path.write_text(rendered_markdown, encoding="utf-8")

    return CompleteDraftReport(
        product_name=PRODUCT_NAME,
        application_number=APPLICATION_NUMBER,
        reporting_period=reporting_period,
        sections=sections,
        overall_grounding_score=overall_grounding,
        total_claims_count=total_claims,
        flagged_claims_count=flagged_claims,
        generated_markdown=rendered_markdown
    )


def assemble_final_pader_report(
    sections: dict[str, GeneratedSectionOutput],
    reporting_period: dict,
    review_session: HumanReviewSession,
    output_filename: str = "pader_bisoprolol_final.md"
) -> CompleteDraftReport:
    """
    Assemble the official FINAL PADER report.
    STRICTLY ENFORCES that all required sections are APPROVED by a human reviewer.
    Raises FinalizationBlockedError if any section is PENDING or FLAGGED.
    """
    is_allowed, blockers = review_session.can_finalize(SECTION_ORDER)
    if not is_allowed:
        raise FinalizationBlockedError(blockers)

    parts: list[str] = []

    p_start = reporting_period.get("start_date", "2024-12-27")
    p_end = reporting_period.get("end_date", "2025-12-26")
    approval_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Document Header - Officially Finalized
    parts.append("# Periodic Adverse Drug Experience Report (PADER)")
    parts.append(f"## {PRODUCT_NAME} — [FINAL APPROVED REPORT]")
    parts.append("")
    parts.append(f"**Application Number**: {APPLICATION_NUMBER}")
    parts.append(f"**Marketing Authorization Holder**: {COMPANY_NAME}")
    parts.append(f"**Reporting Period**: {p_start} to {p_end} ({reporting_period.get('duration_days', 364)} days)")
    parts.append(f"**Regulatory Standard**: United States FDA 21 CFR 314.80")
    parts.append(f"**Human Review Status**: APPROVED (100% Verified by Qualified Safety Reviewer)")
    parts.append(f"**Final Approval Timestamp**: {approval_time}")
    parts.append("")

    # Review Audit Summary Banner
    parts.append("### Human Review & Quality Assurance Sign-off")
    parts.append("| Section | Review Status | Reviewer | Version | Reviewer Notes |")
    parts.append("|---|---|---|---|---|")
    for sid in SECTION_ORDER:
        rec = review_session.records.get(sid)
        title = rec.section_title if rec else sid
        rev = rec.reviewer if rec else "Safety Reviewer"
        ver = f"v{rec.generation_version}" if rec else "v1"
        notes = rec.reviewer_comment or "Approved compliant" if rec else "--"
        parts.append(f"| {title} | **APPROVED** | {rev} | {ver} | {notes} |")

    parts.append("")
    parts.append("---")
    parts.append("## Table of Contents")
    parts.append("")
    for sid in SECTION_ORDER:
        sec_out = sections.get(sid)
        if sec_out:
            parts.append(f"- [{sec_out.section_name}](#{sec_out.section_name.lower().replace(' ', '-').replace('/', '').replace('.', '')})")
    parts.append("- [Appendix: Claim-Level Grounding Audit](#appendix-claim-level-grounding-audit)")
    parts.append("")
    parts.append("---")
    parts.append("")

    # Section Content
    total_claims = 0
    flagged_claims = 0
    all_claims = []

    for sid in SECTION_ORDER:
        sec_out = sections.get(sid)
        if not sec_out:
            continue

        parts.append(sec_out.generated_text)
        parts.append("")
        parts.append("---")
        parts.append("")

        for c in sec_out.claims:
            total_claims += 1
            if c.status in ("FLAGGED", "UNSUPPORTED"):
                flagged_claims += 1
            all_claims.append((sec_out.section_name, c))

    # Appendix
    parts.append("## Appendix: Claim-Level Grounding Audit")
    parts.append("")
    parts.append("The following audit table verifies factual claims against approved deterministic evidence:\n")
    parts.append("| Section | Claim Statement | Evidence ID | Figures | Status | Notes |")
    parts.append("|---|---|---|---|---|---|")

    for sec_name, claim in all_claims:
        clean_text = claim.claim_text.replace("|", "\\|")[:90] + ("..." if len(claim.claim_text) > 90 else "")
        ev_id = claim.evidence_id or "N/A"
        figs = ", ".join(claim.extracted_figures[:4]) if claim.extracted_figures else "--"
        status_icon = "PASS [VERIFIED]" if claim.status == "VERIFIED" else f"WARN [{claim.status}]"
        notes = claim.flag_reason or "Grounded"
        parts.append(f"| {sec_name} | {clean_text} | {ev_id} | {figs} | {status_icon} | {notes} |")

    parts.append("")

    overall_grounding = round((total_claims - flagged_claims) / total_claims, 3) if total_claims > 0 else 1.0
    rendered_markdown = "\n".join(parts)

    out_dir = Path(REPORT_OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / output_filename
    out_path.write_text(rendered_markdown, encoding="utf-8")

    return CompleteDraftReport(
        product_name=PRODUCT_NAME,
        application_number=APPLICATION_NUMBER,
        reporting_period=reporting_period,
        sections=sections,
        overall_grounding_score=overall_grounding,
        total_claims_count=total_claims,
        flagged_claims_count=flagged_claims,
        generated_markdown=rendered_markdown
    )
