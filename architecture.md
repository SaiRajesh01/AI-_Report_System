# System Architecture — GenAR PADER Safety Report Generation & Review Platform

An enterprise-grade, deterministic-first regulatory pharmacovigilance platform built for the **QuickHyre / GenAR AI Engineering Challenge**. Transforms postmarketing safety datasets (ICSRs) into United States FDA Periodic Adverse Drug Experience Reports (**PADER**, 21 CFR 314.80) with mathematically guaranteed numerical accuracy, scoped context isolation, claim-level grounding auditing, and an interactive human-in-the-loop review interface.

---

## 1. End-to-End System Pipeline

```mermaid
flowchart TB
    subgraph INPUT["① Raw Safety Ingestion"]
        DS[("Bisoprolol ICSR Dataset<br/>1,068 rows × 67 columns<br/>.xlsx / .csv")]
    end

    subgraph INGEST["② Validation & Deduplication"]
        LDR["src/data_loader.py & src/validator.py<br/>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━<br/>• Load without mutating raw data<br/>• 67-column schema & type integrity audit<br/>• Group by safetyreportid, keep latest version<br/>• 1,068 rows → 1,024 unique cases (44 deduped)"]
    end

    subgraph ANALYSIS["③ Deterministic Python Analysis (Pure Math — Zero LLM)"]
        direction TB
        A1["case_analysis.py<br/>1,024 cases (1,023 serious / 99.9%, 1 non-serious)"]
        A2["demographic_analysis.py<br/>503 Female, 493 Male; Mean age 70.05y"]
        A3["reaction_analysis.py<br/>3,429 reactions across 1,122 PTs (AKI: 80 cases)"]
        A4["outcome_analysis.py<br/>Case worst-outcome: 68 fatal, 482 hospitalized"]
        A5["trend_analysis.py<br/>Reporting period: 2024-12-27 to 2025-12-26 (+0.39% velocity)"]
        A6["alert_analysis.py<br/>1,023 15-day expedited alerts"]
    end

    subgraph EVIDENCE["④ Scoped Evidence Packet Builder"]
        EA["src/evidence_builder.py<br/>━━━━━━━━━━━━━━━━━━━━━━━━<br/>• Builds isolated SectionEvidencePacket per section<br/>• Attaches evidence_id, calculation def, and source fields<br/>• Enforces strict constraints (SOC omitted, Expectedness out-of-scope)"]
        EV[("report_output/evidence/<br/>CompleteAnalysisPackage.json")]
    end

    subgraph GENERATION["⑤ AI Generation & Grounding Defense Layer"]
        direction TB
        PT["prompts/<br/>System & Section Templates"]
        LLM["src/llm_generator.py<br/>Google Gemini (gemini-2.5-flash)<br/>+ Offline Deterministic Fallback"]
        GV["src/grounding_validator.py<br/>• Numeric verification against evidence<br/>• Flags ungrounded causal / SOC claims"]
    end

    subgraph REVIEW["⑥ Human-in-the-Loop Review UI (Streamlit)"]
        RV["app.py & src/review_manager.py<br/>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━<br/>• Executive Dashboard & KPI Metrics<br/>• Scoped Evidence & Claim Inspector<br/>• ✅ APPROVE (SHA-256 locked)<br/>• 🚩 FLAG (Preserves draft & captures feedback)<br/>• 🔄 REGENERATE (Single-section isolated update)"]
    end

    subgraph OUTPUT["⑦ Multi-Format Report Assembly & Export"]
        RA["src/report_assembler.py<br/>Draft assembler & Claim Audit Appendix"]
        DOCX["src/docx_exporter.py<br/>Word Document Styler (.docx)"]
        RPT["📄 report_output/pader_bisoprolol_final.docx<br/>📄 report_output/pader_bisoprolol_final.md"]
    end

    DS --> LDR
    LDR --> A1 & A2 & A3 & A4 & A5 & A6
    A1 & A2 & A3 & A4 & A5 & A6 --> EV --> EA
    EA --> PT --> LLM --> GV
    GV --> RV
    RV -->|REGENERATE| LLM
    RV -->|APPROVE ALL| RA --> DOCX --> RPT

    style INPUT fill:#e8f4f8,stroke:#2196F3
    style INGEST fill:#e8f5e9,stroke:#4CAF50
    style ANALYSIS fill:#fff3e0,stroke:#FF9800
    style EVIDENCE fill:#f3e5f5,stroke:#9C27B0
    style GENERATION fill:#fce4ec,stroke:#E91E63
    style REVIEW fill:#e0f2f1,stroke:#009688
    style OUTPUT fill:#e8eaf6,stroke:#3F51B5
```

---

## 2. 8 Standard PADER Report Sections

```mermaid
flowchart LR
    subgraph DETERMINISTIC["🔧 Deterministic Sections (Zero Hallucination Risk)"]
        S1["§1 Title / Reporting Period"]
        S7["§7 History of Actions (Absence Confirmed)"]
        S8["§8 Case Index / Line Listing (50 Records)"]
    end

    subgraph LLM_GENERATED["🤖 Scoped LLM Sections (Grounded in Pre-Computed Evidence)"]
        S2["§2 Narrative Summary & Analysis"]
        S3["§3 Summary Analysis of Cases"]
        S4["§4 Reaction / Adverse Event Analysis"]
        S5["§5 Serious Cases / 15-Day Alerts"]
        S6["§6 Trends & Important Observations"]
    end

    style DETERMINISTIC fill:#e8f5e9,stroke:#4CAF50
    style LLM_GENERATED fill:#fce4ec,stroke:#E91E63
```

---

## 3. Scoped Context Isolation & Claim Verification Flow

```mermaid
flowchart LR
    subgraph PYTHON["1. Python Deterministic Analysis"]
        C["Case Analyzer:<br/>1,024 unique cases<br/>1,023 serious (99.9%)<br/>1 non-serious (0.1%)"]
        D["Demographics:<br/>503 Female, 493 Male<br/>Mean Age: 70.05y"]
        R["Reactions:<br/>Top PT: Acute kidney injury (80 cases)"]
    end

    subgraph PACKET["2. Scoped Section Evidence Packet"]
        EP["SectionEvidencePacket<br/>━━━━━━━━━━━━━━━━━━━━━━<br/>section: narrative_summary<br/>product: Bisoprolol<br/>period: 2024-12-27 to 2025-12-26<br/>approved_metrics: {<br/>  total_cases: 1024,<br/>  serious_cases: 1023,<br/>  aki_count: 80<br/>}"]
    end

    subgraph LLM_CALL["3. Structured LLM Generation"]
        PR["System Prompt + Section Template + Scoped Evidence"]
        MD["'During the reporting period, 1,024 cases were received,<br/>of which 1,023 (99.9%) were serious...'"]
    end

    subgraph AUDIT["4. Claim-Level Grounding Audit"]
        G1["✔ 1,024 ∈ approved_metrics [VERIFIED]"]
        G2["✔ 1,023 ∈ approved_metrics [VERIFIED]"]
        G3["✔ 99.9% ∈ approved_metrics [VERIFIED]"]
        G4["✔ No unauthorized SOC/Causal claims detected"]
    end

    C & D & R --> EP --> PR --> MD --> G1 & G2 & G3 & G4

    style PYTHON fill:#fff3e0,stroke:#FF9800
    style PACKET fill:#f3e5f5,stroke:#9C27B0
    style LLM_CALL fill:#fce4ec,stroke:#E91E63
    style AUDIT fill:#e8f5e9,stroke:#4CAF50
```
