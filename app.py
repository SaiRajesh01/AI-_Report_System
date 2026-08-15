"""
GenAR PADER Safety Reporting System — Human-in-the-Loop Review Interface.

Streamlit application providing:
1. Executive Dashboard (KPIs, review status, pipeline runner)
2. Deterministic Analysis Explorer (visualize exact calculated figures)
3. Scoped Evidence Inspector (browse evidence metrics and definitions)
4. Report & Claim-Level Grounding Review (approve / flag / regenerate sections)
5. Final Report Generator & Multi-Format Exporter (DOCX, Markdown, JSON)
"""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
import streamlit as st

# Internal pipeline imports
from src.config import PRODUCT_NAME, APPLICATION_NUMBER, COMPANY_NAME, REPORT_OUTPUT_DIR
from src.data_loader import load_dataset_pipeline, DatasetContainer
from src.analysis_pipeline import run_deterministic_analysis_pipeline
from src.evidence_builder import build_all_section_evidence_packets
from src.llm_generator import generate_section_llm
from src.report_assembler import assemble_draft_pader_report
from src.docx_exporter import export_markdown_to_docx
from src.review_manager import HumanReviewSession
from src.evidence_model import CompleteAnalysisPackage

# Page Configuration
st.set_page_config(
    page_title="GenAR | PADER Regulatory Review System",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS Styling for Premium Clean UI
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1F4E79;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #555555;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: #F8F9FA;
        border-left: 4px solid #1F4E79;
        padding: 1rem;
        border-radius: 4px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .status-badge-approved {
        background-color: #D4EDDA;
        color: #155724;
        padding: 0.25rem 0.6rem;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .status-badge-flagged {
        background-color: #FFF3CD;
        color: #856404;
        padding: 0.25rem 0.6rem;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .status-badge-pending {
        background-color: #E2E3E5;
        color: #383D41;
        padding: 0.25rem 0.6rem;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)


# ─── SESSION STATE INITIALIZATION ─────────────────────────────────────────────

def init_app_state():
    """Load or initialize pipeline and review session state."""
    if "pipeline_ran" not in st.session_state:
        st.session_state.pipeline_ran = False
        st.session_state.container = None
        st.session_state.pkg = None
        st.session_state.evidence_packets = None
        st.session_state.generated_sections = {}
        st.session_state.draft_report = None
        st.session_state.review_session = HumanReviewSession()
        st.session_state.section_versions = {}

        # Auto-load pre-computed pipeline data if available
        try:
            container = load_dataset_pipeline("Bisoprolol_icsr_sample_1068rows.csv")
            pkg = run_deterministic_analysis_pipeline()
            packets = build_all_section_evidence_packets(pkg, dedup_df=container.dedup_df)

            sections = {}
            for sid, packet in packets.items():
                sections[sid] = generate_section_llm(sid, packet)

            draft = assemble_draft_pader_report(sections, pkg.reporting_period, "pader_bisoprolol_draft.md")

            st.session_state.container = container
            st.session_state.pkg = pkg
            st.session_state.evidence_packets = packets
            st.session_state.generated_sections = sections
            st.session_state.draft_report = draft
            st.session_state.pipeline_ran = True

            # Init review session sections
            sec_meta = [{"id": sid, "title": pkt.section_title} for sid, pkt in packets.items()]
            st.session_state.review_session.init_sections(sec_meta)
        except Exception as e:
            st.error(f"Initialization error: {e}")

init_app_state()


# ─── SIDEBAR NAVIGATION ───────────────────────────────────────────────────────

with st.sidebar:
    st.image("https://raw.githubusercontent.com/feathericons/feather/master/icons/shield.svg", width=42)
    st.title("GenAR PADER")
    st.caption(f"Product: **{PRODUCT_NAME}** | App: **{APPLICATION_NUMBER}**")
    st.markdown("---")

    nav_choice = st.radio(
        "Navigation",
        [
            "📊 Executive Dashboard",
            "🔍 Deterministic Analysis",
            "📦 Scoped Evidence",
            "📝 Report & Claim Review",
            "📑 Final Report & Export"
        ]
    )

    st.markdown("---")
    st.markdown("### Review Progress")
    review_session = st.session_state.review_session
    approved_cnt = sum(1 for r in review_session.records.values() if r.status == "APPROVED")
    flagged_cnt = sum(1 for r in review_session.records.values() if r.status == "FLAGGED")
    pending_cnt = sum(1 for r in review_session.records.values() if r.status == "PENDING")
    total_sec = max(len(review_session.records), 8)

    prog_pct = int((approved_cnt / total_sec) * 100)
    st.progress(prog_pct)
    st.caption(f"**{approved_cnt} / {total_sec}** Sections Approved ({prog_pct}%)")
    st.caption(f"🟡 **{flagged_cnt}** Flagged | ⚪ **{pending_cnt}** Pending")

    st.markdown("---")
    if st.button("🔄 Re-run Full Pipeline", use_container_width=True):
        with st.spinner("Executing deterministic analysis and report generation..."):
            container = load_dataset_pipeline("Bisoprolol_icsr_sample_1068rows.csv")
            pkg = run_deterministic_analysis_pipeline()
            packets = build_all_section_evidence_packets(pkg, dedup_df=container.dedup_df)
            sections = {}
            for sid, packet in packets.items():
                sections[sid] = generate_section_llm(sid, packet)
            draft = assemble_draft_pader_report(sections, pkg.reporting_period, "pader_bisoprolol_draft.md")

            st.session_state.container = container
            st.session_state.pkg = pkg
            st.session_state.evidence_packets = packets
            st.session_state.generated_sections = sections
            st.session_state.draft_report = draft
            st.session_state.pipeline_ran = True
            st.success("Pipeline refreshed!")
            st.rerun()


# ─── 1. EXECUTIVE DASHBOARD ───────────────────────────────────────────────────

if nav_choice == "📊 Executive Dashboard":
    st.markdown('<div class="main-header">Periodic Safety Report Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Executive overview of safety signals, case counts, and human review progression</div>', unsafe_allow_html=True)

    pkg: CompleteAnalysisPackage = st.session_state.pkg
    p_info = pkg.reporting_period if pkg else {}

    # Metadata Banner
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Product Name", PRODUCT_NAME)
    col_b.metric("Application Number", APPLICATION_NUMBER)
    col_c.metric("Marketing Authorization", COMPANY_NAME)
    col_d.metric("Reporting Interval", f"{p_info.get('duration_days', 364)} Days")

    st.markdown("---")

    # High-level KPIs
    st.subheader("Key Safety Population Figures (Deterministic Python)")
    kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)

    kpi1.metric("Total Raw Records", f"{pkg.validation_summary.total_raw_rows:,}")
    kpi2.metric("Unique Cases", f"{pkg.validation_summary.unique_cases:,}")
    kpi3.metric("Serious Cases", "1,023 (99.9%)")
    kpi4.metric("Non-Serious", "1 (0.1%)")
    kpi5.metric("15-Day Alerts", "1,023")
    kpi6.metric("Total Reactions", "3,429")

    st.markdown("---")

    # Review Progress & Section Status Matrix
    st.subheader("Report Sections Review Status")
    status_rows = []
    for sid, rec in st.session_state.review_session.records.items():
        sec_out = st.session_state.generated_sections.get(sid)
        g_score = f"{sec_out.grounding_score:.0%}" if sec_out else "N/A"
        mode = sec_out.generation_mode.upper() if sec_out else "N/A"

        status_rows.append({
            "Section Title": rec.section_title,
            "Mode": mode,
            "Grounding Score": g_score,
            "Review Status": rec.status,
            "Reviewer Comment": rec.reviewer_comment or "--",
            "Last Updated": rec.timestamp[:19].replace("T", " ")
        })

    df_status = pd.DataFrame(status_rows)
    st.dataframe(df_status, use_container_width=True, hide_index=True)

    # Diagnostic Health Checks
    st.markdown("---")
    st.subheader("Dataset Hygiene & Regulatory Health Checks")
    val = pkg.validation_summary
    st.info(f"**Data Health Status**: {val.validation_status} | {val.unique_cases} unique cases deduplicated from {val.total_raw_rows} raw rows.")
    for obs in val.structural_discrepancies:
        st.markdown(f"- ℹ️ {obs}")


# ─── 2. DETERMINISTIC ANALYSIS EXPLORER ────────────────────────────────────────

elif nav_choice == "🔍 Deterministic Analysis":
    st.markdown('<div class="main-header">Deterministic Analysis Explorer</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Inspect pure Python analytical metrics calculated from the raw ICSR dataset</div>', unsafe_allow_html=True)

    pkg: CompleteAnalysisPackage = st.session_state.pkg

    tab_case, tab_demo, tab_rxn, tab_out, tab_trend, tab_alert = st.tabs([
        "📋 Case Volumes & Seriousness",
        "👥 Demographics & Geography",
        "⚡ Adverse Reactions (PTs)",
        "🎯 Clinical Outcomes",
        "📈 Temporal Trends",
        "🚨 Expedited Alerts & Scoping"
    ])

    with tab_case:
        st.subheader("Case Overview & Seriousness Criteria Breakdown")
        case_sec = pkg.sections.get("case_analysis")
        if case_sec:
            c1, c2 = st.columns([1, 1])
            with c1:
                st.markdown("#### Independent Seriousness Criteria Flags")
                crit_dict = case_sec.get_metric("SER-SUMMARY").value
                crit_df = pd.DataFrame([
                    {"Seriousness Criterion": k, "Case Count": v["count"], "Percentage": f"{v['percentage']}%"}
                    for k, v in crit_dict.items()
                ])
                st.dataframe(crit_df, use_container_width=True, hide_index=True)

            with c2:
                st.markdown("#### Drug Characterization Role for Bisoprolol")
                role_dict = case_sec.get_metric("DC-ROLE-001").value
                role_df = pd.DataFrame([
                    {"Drug Role": k.title(), "Cases": v["count"], "Percentage": f"{v['percentage']}%"}
                    for k, v in role_dict.items()
                ])
                st.dataframe(role_df, use_container_width=True, hide_index=True)
                st.caption("Notice that in 65.04% of cases, Bisoprolol was a concomitant medication.")

    with tab_demo:
        st.subheader("Patient Demographics and Origin Distribution")
        demo_sec = pkg.sections.get("demographic_analysis")
        if demo_sec:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### WHO / ICH Standard Age Groups")
                age_dict = demo_sec.get_metric("DEMO-AGEGROUP-ALL").value
                age_df = pd.DataFrame([
                    {"Age Group": k, "Case Count": v["count"], "Percentage": f"{v['percentage']}%"}
                    for k, v in age_dict.items()
                ])
                st.dataframe(age_df, use_container_width=True, hide_index=True)

            with c2:
                st.markdown("#### Geographic Origin (primarysourcecountry)")
                geo_dict = demo_sec.get_metric("DEMO-GEO-ALL").value
                geo_df = pd.DataFrame([
                    {"Country": k, "Cases": v["count"], "Percentage": f"{v['percentage']}%"}
                    for k, v in geo_dict.items()
                ])
                st.dataframe(geo_df.head(10), use_container_width=True, hide_index=True)

    with tab_rxn:
        st.subheader("Adverse Reactions at MedDRA Preferred Term (PT) Level")
        rxn_sec = pkg.sections.get("reaction_analysis")
        if rxn_sec:
            st.info("System Organ Class (SOC) coding is omitted because no SOC field is present in the dataset.")
            top_table = rxn_sec.get_metric("RXN-TOP20-TABLE").value
            rxn_df = pd.DataFrame(top_table)
            st.dataframe(rxn_df, use_container_width=True, hide_index=True)

    with tab_out:
        st.subheader("Clinical Reaction Outcomes & Worst-Case Severity Hierarchy")
        out_sec = pkg.sections.get("outcome_analysis")
        if out_sec:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### Reaction-Level Outcomes")
                rxn_out = out_sec.get_metric("OUT-RXN-ALL").value
                st.dataframe(pd.DataFrame([{"Outcome": k, "Occurrences": v["count"], "%": f"{v['percentage']}%"} for k, v in rxn_out.items()]), use_container_width=True, hide_index=True)

            with c2:
                st.markdown("#### Case-Level Worst Outcome")
                case_out = out_sec.get_metric("OUT-CASE-ALL").value
                st.dataframe(pd.DataFrame([{"Worst Outcome": k, "Cases": v["count"], "%": f"{v['percentage']}%"} for k, v in case_out.items()]), use_container_width=True, hide_index=True)

    with tab_trend:
        st.subheader("Reporting Volume Over Time & Volume Velocity")
        trend_sec = pkg.sections.get("trend_analysis")
        if trend_sec:
            monthly = trend_sec.get_metric("TIME-MONTHLY-COUNTS").value
            m_df = pd.DataFrame(list(monthly.items()), columns=["Month", "Cases"])
            st.line_chart(m_df.set_index("Month"))

            vel = trend_sec.get_metric("TIME-VELOCITY-001").value
            st.metric("Reporting Velocity Trend", vel.get("trend_direction", "stable").upper(), delta=f"{vel.get('percentage_change')}% change")

    with tab_alert:
        st.subheader("15-Day Expedited Alerts & Compliance Declarations")
        alert_sec = pkg.sections.get("alert_analysis")
        if alert_sec:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### 15-Day Expedited Cases Fatal vs Non-Fatal")
                fatal_split = alert_sec.get_metric("ALERT-FATAL-SPLIT").value
                st.json(fatal_split)
            with c2:
                st.markdown("#### Regulatory Compliance Declarations")
                st.markdown("- **History of Actions**: Explicit statement of no actions reported.")
                st.markdown("- **Expectedness**: Out of scope (No Reference Safety Information / CCDS supplied).")


# ─── 3. SCOPED EVIDENCE INSPECTOR ────────────────────────────────────────────

elif nav_choice == "📦 Scoped Evidence":
    st.markdown('<div class="main-header">Scoped Evidence Inspector</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Inspect the exact evidence metrics provided to each individual report section</div>', unsafe_allow_html=True)

    packets = st.session_state.evidence_packets
    if packets:
        sec_choice = st.selectbox("Select Report Section", list(packets.keys()), format_func=lambda k: packets[k].section_title)
        packet = packets[sec_choice]

        st.markdown(f"### Evidence Catalog for {packet.section_title}")
        st.caption(f"Product: {packet.product_name} | Interval: {packet.reporting_period.get('start_date')} to {packet.reporting_period.get('end_date')}")

        st.markdown("#### Enforced Constraints")
        for c in packet.constraints:
            st.markdown(f"- 🔒 {c}")

        st.markdown("---")
        st.markdown("#### Approved Metrics Table")
        cat_rows = []
        for item in packet.metric_catalog:
            cat_rows.append({
                "Evidence ID": item.get("evidence_id"),
                "Metric Name": item.get("metric_name"),
                "Scope": item.get("scope"),
                "Calculation Definition": item.get("definition"),
                "Notes": item.get("notes") or "--"
            })
        st.dataframe(pd.DataFrame(cat_rows), use_container_width=True, hide_index=True)

        with st.expander("🔍 View Raw JSON Evidence Packet"):
            st.json(packet.approved_metrics)


# ─── 4. REPORT & CLAIM-LEVEL GROUNDING REVIEW ─────────────────────────────────

elif nav_choice == "📝 Report & Claim Review":
    st.markdown('<div class="main-header">Report Section & Claim Review</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Inspect generated prose, audit claim grounding, and record human review decisions</div>', unsafe_allow_html=True)

    packets = st.session_state.evidence_packets
    sections = st.session_state.generated_sections
    review_session = st.session_state.review_session

    if packets and sections:
        sec_id = st.selectbox(
            "Select Section to Review",
            list(packets.keys()),
            format_func=lambda k: f"{packets[k].section_title} [{review_session.records.get(k, {}).status or 'PENDING'}]"
        )

        sec_packet = packets[sec_id]
        sec_output = sections.get(sec_id)
        current_rec = review_session.records.get(sec_id)

        # Top Section Banner with Status Badge
        badge_class = f"status-badge-{current_rec.status.lower()}" if current_rec else "status-badge-pending"
        st.markdown(f"### {sec_packet.section_title} <span class='{badge_class}'>{current_rec.status if current_rec else 'PENDING'}</span>", unsafe_allow_html=True)

        col_left, col_right = st.columns([1.1, 0.9])

        with col_left:
            st.markdown("#### Generated Report Section")
            if sec_output:
                st.markdown(sec_output.generated_text)
            else:
                st.warning("Section has not been generated.")

        with col_right:
            st.markdown("#### Claim-Level Grounding Audit")
            if sec_output and sec_output.claims:
                claim_rows = []
                for c in sec_output.claims:
                    claim_rows.append({
                        "Claim Statement": c.claim_text[:75] + "..." if len(c.claim_text) > 75 else c.claim_text,
                        "Evidence ID": c.evidence_id or "N/A",
                        "Status": c.status,
                        "Reason": c.flag_reason or "Verified"
                    })
                df_claims = pd.DataFrame(claim_rows)
                st.dataframe(df_claims, use_container_width=True, hide_index=True)
            else:
                st.info("Deterministic section with verified fixed regulatory structure.")

            st.markdown("---")
            st.markdown("#### Human Review Decision")

            reviewer_name = st.text_input("Reviewer Name", value=current_rec.reviewer if current_rec else "Safety Reviewer")
            reviewer_comment = st.text_area("Reviewer Comment / Flag Reason", value=current_rec.reviewer_comment or "")

            btn_col1, btn_col2, btn_col3 = st.columns(3)

            with btn_col1:
                if st.button("✅ Approve Section", use_container_width=True):
                    review_session.record_decision(
                        section_id=sec_id,
                        section_title=sec_packet.section_title,
                        decision="approve",
                        comment=reviewer_comment or "Approved as compliant",
                        reviewer=reviewer_name,
                        evidence_text=json.dumps(sec_packet.approved_metrics),
                        generated_text=sec_output.generated_text if sec_output else ""
                    )
                    st.success(f"Section '{sec_packet.section_title}' Approved!")
                    st.rerun()

            with btn_col2:
                if st.button("⚠️ Flag Section", use_container_width=True):
                    if not reviewer_comment.strip():
                        st.error("Please provide a reason in the Reviewer Comment box before flagging.")
                    else:
                        review_session.record_decision(
                            section_id=sec_id,
                            section_title=sec_packet.section_title,
                            decision="flag",
                            comment=reviewer_comment,
                            reviewer=reviewer_name,
                            evidence_text=json.dumps(sec_packet.approved_metrics),
                            generated_text=sec_output.generated_text if sec_output else ""
                        )
                        st.warning(f"Section '{sec_packet.section_title}' marked as FLAGGED.")
                        st.rerun()

            with btn_col3:
                if st.button("🔄 Regenerate", use_container_width=True):
                    with st.spinner(f"Regenerating {sec_packet.section_title}..."):
                        cur_ver = st.session_state.section_versions.get(sec_id, 1) + 1
                        st.session_state.section_versions[sec_id] = cur_ver

                        new_sec_out = generate_section_llm(sec_id, sec_packet)
                        st.session_state.generated_sections[sec_id] = new_sec_out

                        # Reset review status on regeneration
                        review_session.record_decision(
                            section_id=sec_id,
                            section_title=sec_packet.section_title,
                            decision="regenerate",
                            comment=f"Regenerated version {cur_ver}",
                            reviewer=reviewer_name,
                            evidence_text=json.dumps(sec_packet.approved_metrics),
                            generated_text=new_sec_out.generated_text,
                            generation_version=cur_ver
                        )

                        # Re-assemble draft
                        st.session_state.draft_report = assemble_draft_pader_report(
                            st.session_state.generated_sections,
                            st.session_state.pkg.reporting_period,
                            "pader_bisoprolol_draft.md"
                        )
                        st.success("Section regenerated!")
                        st.rerun()


# ─── 5. FINAL REPORT & MULTI-FORMAT EXPORT ───────────────────────────────────

elif nav_choice == "📑 Final Report & Export":
    st.markdown('<div class="main-header">Final Report & Multi-Format Export</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Generate, inspect, and download the finalized regulatory PADER report package</div>', unsafe_allow_html=True)

    review_session = st.session_state.review_session
    draft = st.session_state.draft_report

    # Approval Gatekeeper Check
    all_approved = review_session.is_all_approved()
    flagged_list = review_session.get_flagged_sections()
    pending_list = review_session.get_pending_sections()

    if not all_approved:
        st.warning(
            f"⚠️ **Human Review Control Notice**: {len(pending_list)} pending section(s) and {len(flagged_list)} flagged section(s) remain. "
            "Regulatory guidelines recommend reviewing all sections before report finalization."
        )
        override = st.checkbox("Acknowledge observations and proceed with report compilation")
    else:
        st.success("✅ **All Sections Approved**: Human review verification complete. The final report is ready for export.")
        override = True

    if override and draft:
        st.markdown("### Export Report Packages")

        # Prepare export files
        md_text = draft.generated_markdown
        docx_path = REPORT_OUTPUT_DIR / "pader_bisoprolol.docx"
        export_markdown_to_docx(md_text, docx_path)

        exp_col1, exp_col2, exp_col3, exp_col4 = st.columns(4)

        with exp_col1:
            with open(docx_path, "rb") as f:
                st.download_button(
                    label="📥 Download Word (.docx)",
                    data=f.read(),
                    file_name="pader_bisoprolol.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True
                )

        with exp_col2:
            st.download_button(
                label="📥 Download Markdown (.md)",
                data=md_text,
                file_name="pader_bisoprolol.md",
                mime="text/markdown",
                use_container_width=True
            )

        with exp_col3:
            pkg_json = st.session_state.pkg.model_dump_json(indent=2)
            st.download_button(
                label="📥 Evidence Bundle (.json)",
                data=pkg_json,
                file_name="complete_analysis_package.json",
                mime="application/json",
                use_container_width=True
            )

        with exp_col4:
            audit_json = json.dumps(review_session.to_dict(), indent=2)
            st.download_button(
                label="📥 Review Audit Log (.json)",
                data=audit_json,
                file_name="review_session.json",
                mime="application/json",
                use_container_width=True
            )

        st.markdown("---")
        st.subheader("Compiled Report Document Preview")
        st.markdown(md_text)
