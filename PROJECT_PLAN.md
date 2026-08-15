# GenAR AI Engineering Challenge — PROJECT PLAN

## A. Assessment Understanding

### What This Challenge Asks
Build a Python prototype that transforms Bisoprolol ICSR safety data (1,068 rows / 1,024 unique cases) into a PADER-style regulatory report. The system must:
- Use **deterministic Python** for all calculations (not the LLM)
- Feed the LLM a **scoped evidence packet** (not raw CSV)
- Keep all generated claims **grounded in computed evidence**
- Include a **human review step** before finalization
- Be **extensible** toward other report types (PSUR, PBRER, DSUR, CSR)

### Evaluation Criteria (from challenge doc)
| Area | What they want |
|---|---|
| AI fundamentals | LLM used only where it earns its keep |
| Context engineering | Right information, at the right step, nothing extra |
| Prompt design | Clear, section-specific, reliable |
| Architecture | Sensible decomposition — not one LLM call |
| Agent/tool judgment | No agents/tools unless justified |
| Grounding | Every claim traceable to data |
| Evaluation | How to verify output correctness |
| Generalization | Could grow past PADER without rewrite |
| Execution | It runs and produces a report |

---

## B. Dataset Analysis

### Schema Overview
- **File**: `Bisoprolol_icsr_sample_1068rows.xlsx` (67 columns, 1,068 rows)
- **Format**: Excel (.xlsx), not CSV as stated in challenge docs. Code must handle both.
- **Unique Cases**: 1,024 distinct `safetyreportid` values
- **Duplicates**: 38 cases with 2 versions, 3 cases with 3 versions (983 single-version)
- **Reporting Period**: 27 Dec 2024 → 26 Dec 2025 (364 days, derived from `receivedate`)

### Key Column Groups
| Group | Columns | Notes |
|---|---|---|
| Case ID | `safetyreportid`, `safetyreportversion`, `companynumb` | Version dedup required |
| Dates | `receivedate`, `receiptdate`, `transmissiondate`, `report_date` | Integer YYYYMMDD format (except `report_date` = datetime) |
| Seriousness | `serious`, `seriousnessdeath`, `seriousnesslifethreatening`, `seriousnesshospitalization`, `seriousnessdisabling`, `seriousnesscongenitalanomali`, `seriousnessother` | Independent yes/no flags |
| Patient | `patient_patientsex`, `patient_patientonsetage`, `patient_patientonsetageunit`, `patient_patientagegroup`, `patient_patientweight` | Age: 8.5% missing; Sex: 2.8% missing |
| Reactions | `patient_reaction_reactionmeddrapt`, `patient_reaction_reactionoutcome` | Comma-separated multi-value |
| Drugs | `patient_drug_drugcharacterization`, `patient_drug_medicinalproduct`, `patient_drug_drugindication`, `patient_drug_actiondrug` | Comma-separated multi-value |
| Geography | `primarysourcecountry`, `occurcountry`, `primarysource_reportercountry` | 21 countries; "eu" is a common value |
| Reporter | `primarysource_qualification` | physician/pharmacist/other HP/consumer |
| Report type | `reporttype`, `fulfillexpeditecriteria` | spontaneous/study; expedited yes/no |
| Narrative | `patient_summary_narrativeincludeclinical` | ALL are stubs: "CASE EVENT DATE: YYYYMMDD" |

### Critical Data Characteristics
1. **Seriousness**: 1,023/1,024 cases are serious (99.9%)
2. **15-Day Alerts**: 1,023/1,024 meet expedite criteria (nearly identical to serious)
3. **Sex**: Female 503, Male 493, Unknown 28
4. **Age**: Mean 70.4y, Median 72y (when unit=year, n=975). 8.5% missing.
5. **Top Countries**: EU (345), UK (281), France (185), Canada (56), Italy (51)
6. **Bisoprolol Role**: Suspect in 340 cases (33%), Concomitant in 666 (65%), Interacting in 17 (2%)
7. **Top PTs**: Acute kidney injury (80), Drug ineffective (54), Hypotension (46), Drug interaction (43)
8. **Outcomes**: Recovered 1,347, Unknown 1,135, Not recovered 569, Fatal 137 (reaction-level)
9. **Narratives**: All 692 non-null narratives are identical "CASE EVENT DATE:" stubs — no useful clinical text
10. **No SOC column**: Only Preferred Terms available

### Deduplication Strategy
- Keep latest `safetyreportversion` per `safetyreportid`
- Use deduplicated set (1,024 cases) for all case-level counts
- Reaction-level counts: explode comma-separated PTs from the deduplicated cases → 3,429 reactions (1,122 unique PTs)

> [!IMPORTANT]
> The sample report uses 3,648 total reactions (counting all 1,068 rows including older versions). Our system must use deduplicated cases (3,429 reactions from 1,024 cases) and explicitly document this decision.

---

## C. Discrepancies: Sample Report vs Actual Dataset

| # | Sample Report Claims | Actual Data Reality | Our Approach |
|---|---|---|---|
| 1 | **SOC-level tabulation** with "Blood and lymphatic system disorders" etc. | **No SOC column** in dataset; only PT-level data | Report at PT level; explicitly note SOC unavailable |
| 2 | Classifies all events as **"Unlabelled"** | **No product label/CCDS** supplied | State expectedness is out of scope per challenge guide |
| 3 | **3,648 reaction instances** total | 3,648 from all rows; **3,429 from unique cases** | Use 3,429 (deduplicated); document the difference |
| 4 | Detailed **case narratives** for top PTs (demographics, comorbidities, clinical course) | Narratives are **all stubs** ("CASE EVENT DATE: ...") | Generate PT-level summaries from structured fields only; do NOT fabricate clinical detail |
| 5 | **CCDS/Safety Section** with indications, contraindications, warnings, drug interactions | **No CCDS/label document** supplied | Omit or mark as "not available for this dataset" |
| 6 | Cumulative columns all show 0 | **No prior period data** — 0 is correct | Show cumulative as N/A (first report period) |
| 7 | Solicited (Study)=10, Spontaneous varies | `reporttype`: spontaneous=1,014, study=10 | **Matches** — use actual field values |
| 8 | All cases treated as Bisoprolol-related | Bisoprolol is **suspect in only 33%** of cases | Surface this critical distinction clearly |

> [!CAUTION]
> The sample report contains SOC classifications and detailed clinical narratives that **cannot be reproduced from the supplied dataset**. Copying these unsupported elements would violate the challenge's grounding requirement. Our system will acknowledge these gaps explicitly.

---

## D. Implementation Plan

### Phase 1: Foundation (Steps 1–3)
1. **Data ingestion & validation** — load Excel/CSV, validate schema, detect anomalies
2. **Case deduplication** — latest version per `safetyreportid`
3. **Field parsers** — comma-separated multi-value explosion, date parsing, age bucketing

### Phase 2: Deterministic Analysis Modules (Steps 4–9)
4. **Case overview analysis** — total, serious/non-serious, expedited, report type, reporter qualification
5. **Demographics analysis** — age groups, sex, country distribution
6. **Reaction analysis** — PT frequency (all, serious only), reaction-outcome cross-tab
7. **Seriousness analysis** — criteria breakdown (death, life-threatening, hospitalization, etc.)
8. **Temporal analysis** — monthly/quarterly case counts, trends
9. **Drug characterization analysis** — suspect vs concomitant, Bisoprolol indications

### Phase 3: Evidence Assembly & LLM Integration (Steps 10–12)
10. **Evidence model** — structured JSON evidence packets per report section
11. **Prompt templates** — section-specific templates with grounding constraints
12. **LLM section generator** — calls LLM with evidence packets, validates output

### Phase 4: Report Assembly & Human Review (Steps 13–15)
13. **Report assembler** — combines generated sections into final document
14. **Human review workflow** — section-by-section approve/flag/reject mechanism
15. **Report renderer** — Markdown output (+ optional HTML/PDF)

### Phase 5: Testing, Documentation & Delivery (Steps 16–18)
16. **Tests** — unit tests, integration tests, evidence grounding checks
17. **README & documentation** — architecture, prompts, decisions, limitations
18. **Version 1 design document** — extensibility strategy

---

## E. Project Folder Structure

```
genar-challenge/
├── README.md                          # How to run, architecture, decisions, limitations
├── architecture.md                    # Mermaid architecture diagram
├── requirements.txt                   # Python dependencies
├── .env.example                       # API key template
│
├── src/
│   ├── __init__.py
│   ├── main.py                        # CLI entry point: run the full pipeline
│   ├── config.py                      # Report type config, section definitions
│   │
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── loader.py                  # Load CSV/XLSX, validate schema
│   │   └── deduplicator.py            # Case-level deduplication logic
│   │
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── base.py                    # Abstract base class for analysis modules
│   │   ├── case_overview.py           # Total cases, serious/non-serious, expedited
│   │   ├── demographics.py            # Age groups, sex, country
│   │   ├── reactions.py               # PT frequency, serious reactions
│   │   ├── seriousness.py             # Seriousness criteria breakdown
│   │   ├── outcomes.py                # Outcome distributions
│   │   ├── temporal.py                # Monthly/quarterly trends
│   │   └── drug_characterization.py   # Suspect/concomitant, indications
│   │
│   ├── evidence/
│   │   ├── __init__.py
│   │   ├── model.py                   # Evidence dataclasses / typed dicts
│   │   ├── assembler.py               # Build section-specific evidence packets
│   │   └── validator.py               # Validate evidence completeness
│   │
│   ├── generation/
│   │   ├── __init__.py
│   │   ├── llm_client.py              # LLM API wrapper (model-agnostic)
│   │   ├── section_generator.py       # Generate one section from evidence
│   │   └── grounding_checker.py       # Verify claims match evidence
│   │
│   ├── report/
│   │   ├── __init__.py
│   │   ├── assembler.py               # Combine sections into full report
│   │   └── renderer.py                # Markdown / HTML output
│   │
│   ├── review/
│   │   ├── __init__.py
│   │   └── reviewer.py                # Human review: approve/flag/reject per section
│   │
│   └── report_types/
│       ├── __init__.py
│       └── pader.py                   # PADER-specific config: sections, analyses needed
│
├── prompts/
│   ├── system.md                      # Base system prompt
│   ├── narrative_summary.md           # Narrative Summary and Analysis section
│   ├── case_summary.md                # Summary Analysis of Cases section
│   ├── reaction_analysis.md           # Reaction / Adverse Event Analysis
│   ├── serious_cases.md               # Serious Cases / 15-Day Alerts
│   ├── trends.md                      # Trends and Important Observations
│   ├── history_of_actions.md          # History of Actions
│   └── case_listing.md                # Case Index / Listing
│
├── tests/
│   ├── __init__.py
│   ├── test_loader.py
│   ├── test_deduplication.py
│   ├── test_analysis_modules.py
│   ├── test_evidence_assembly.py
│   ├── test_grounding.py
│   └── test_report_assembly.py
│
├── report_output/
│   └── pader_bisoprolol.md            # Generated PADER report
│
└── version1/
    └── design.md                      # V1 extension strategy
```

---

## F. Deterministic Analysis Modules

All calculations performed by Python. The LLM never computes numbers.

### F1. Case Overview (`analysis/case_overview.py`)
| Metric | Computation |
|---|---|
| Total cases | Count unique `safetyreportid` after dedup |
| Serious cases | Count where `serious == 'serious'` |
| Non-serious cases | Count where `serious == 'not serious'` |
| 15-day Alert cases | Count where `fulfillexpeditecriteria == 'yes'` |
| Report type split | Value counts of `reporttype` |
| Reporter qualification | Value counts of `primarysource_qualification` |

### F2. Demographics (`analysis/demographics.py`)
| Metric | Computation |
|---|---|
| Age groups | Bucket `patient_patientonsetage` (where unit=year) into: Neonate (0–<1mo), Infant, Child, Adolescent, Adult (18–64), Elderly (≥65y). Handle non-year units by converting. |
| Sex | Value counts of `patient_patientsex` (male/female/unknown) |
| Country | Value counts of `primarysourcecountry`, with ISO normalization (e.g., "IE"→Ireland) |
| Age statistics | Mean, median, min, max of age-in-years |

### F3. Reaction Analysis (`analysis/reactions.py`)
| Metric | Computation |
|---|---|
| All PTs | Explode comma-separated `patient_reaction_reactionmeddrapt`, frequency count |
| Top N PTs | Top 20 most frequent PTs |
| Serious PTs | PTs from serious cases only (separate count) |
| PT-outcome cross-tab | For each top PT: outcome distribution |
| PT by sex | For each top PT: male/female/unknown split |
| PT by age group | For each top PT: age group distribution |

### F4. Seriousness Criteria (`analysis/seriousness.py`)
| Metric | Computation |
|---|---|
| Criteria breakdown | Count cases where each seriousness flag = 'yes' |
| Multi-criteria cases | Cases meeting >1 seriousness criterion |
| Fatal cases | `seriousnessdeath == 'yes'` count |

### F5. Outcome Analysis (`analysis/outcomes.py`)
| Metric | Computation |
|---|---|
| Reaction outcomes | Value counts of exploded `patient_reaction_reactionoutcome` |
| Case-level outcome | Worst outcome per case (fatal > not recovered > recovering > recovered > unknown) |

### F6. Temporal Analysis (`analysis/temporal.py`)
| Metric | Computation |
|---|---|
| Monthly counts | Cases per month based on `receivedate` |
| Quarterly counts | Cases per quarter |
| Trend direction | Simple comparison: first-half vs second-half volume |
| PT temporal trends | Top PTs by month (detect concentration in specific periods) |

### F7. Drug Characterization (`analysis/drug_characterization.py`)
| Metric | Computation |
|---|---|
| Bisoprolol role | suspect/concomitant/interacting counts |
| Bisoprolol indications | Value counts of indication where drug matches Bisoprolol |
| Concomitant drugs | Most common co-reported drugs |
| Action taken | Value counts of `patient_drug_actiondrug` for Bisoprolol |

---

## G. Evidence Model

### Design Principle
Each report section receives a typed `EvidencePacket` — a self-contained JSON structure that contains **only** the pre-computed data that section needs. The LLM never sees raw data, only processed results.

### Core Evidence Schema

```python
@dataclass
class EvidencePacket:
    """Self-contained evidence for one report section."""
    section_id: str                    # e.g., "narrative_summary"
    report_type: str                   # e.g., "PADER"
    product_name: str                  # e.g., "Bisoprolol"
    reporting_period: ReportingPeriod  # start_date, end_date
    analyses: dict[str, AnalysisResult]  # keyed by analysis name
    metadata: EvidenceMetadata         # generation timestamp, data version

@dataclass
class ReportingPeriod:
    start_date: str       # "2024-12-27"
    end_date: str         # "2025-12-26"
    duration_days: int    # 364

@dataclass
class AnalysisResult:
    analysis_name: str        # e.g., "case_overview"
    computed_at: str           # ISO timestamp
    figures: dict[str, Any]    # the actual numbers/tables
    notes: list[str]           # e.g., ["Deduplicated by latest safetyreportversion"]

@dataclass
class EvidenceMetadata:
    dataset_file: str
    total_rows: int
    unique_cases: int
    dedup_method: str
    generated_at: str
```

### Section → Evidence Mapping

| Section | Required Analyses | Key Evidence Fields |
|---|---|---|
| **Reporting Period** | `case_overview` | product, period dates, total_cases, application_number |
| **Narrative Summary** | `case_overview`, `demographics`, `reactions`, `seriousness`, `outcomes` | All high-level figures: totals, top reactions, demographics summary |
| **Summary Analysis of Cases** | `case_overview`, `demographics`, `seriousness` | Detailed case counts, age/sex/country tables, reporter qualification |
| **Reaction Analysis** | `reactions`, `temporal` | PT frequency table, PT-by-age, PT-by-sex, PT trends |
| **Serious Cases / 15-Day Alerts** | `case_overview`, `seriousness`, `reactions` | Expedited count, fatal/non-fatal, seriousness criteria breakdown |
| **Trends & Observations** | `temporal`, `reactions`, `demographics` | Monthly trends, notable patterns |
| **History of Actions** | (none — no data supplied) | Explicit "no actions supplied" flag |
| **Case Index / Listing** | Raw deduplicated case data | Case-level table: ID, PTs, serious, date, country, outcome |

### Evidence Serialization
Evidence packets serialize to JSON for:
1. Passing to the LLM prompt
2. Archiving alongside the generated report (for traceability)
3. Inspection during human review

---

## H. Human Review Workflow

### Design
A **CLI-driven review workflow** where the human reviewer examines each generated section and decides:
- **APPROVE** → section goes into the final report as-is
- **FLAG** → section is included but marked as "flagged for further review"
- **REJECT** → section is excluded from the final report, with a reason logged
- **REGENERATE** → re-run generation with optional reviewer notes

### Workflow Steps

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  1. Evidence      │────→│  2. Generation    │────→│  3. Review        │
│  (deterministic)  │     │  (LLM per section)│     │  (human)          │
└──────────────────┘     └──────────────────┘     └──────────────────┘
                                                          │
                                              ┌───────────┼───────────┐
                                              ▼           ▼           ▼
                                          APPROVE      FLAG       REJECT
                                              │           │           │
                                              ▼           ▼           ▼
                                        ┌─────────────────────────────┐
                                        │  4. Final Report Assembly   │
                                        └─────────────────────────────┘
```

### Review Record
Each decision is stored as a `ReviewDecision`:
```python
@dataclass
class ReviewDecision:
    section_id: str
    reviewer: str            # identifier or "cli-user"
    decision: str            # approve | flag | reject | regenerate
    reason: str | None       # mandatory for flag/reject
    timestamp: str
    evidence_hash: str       # SHA256 of the evidence packet
    generated_text_hash: str # SHA256 of the generated section
```

### Implementation Approach
- **Version 0**: Interactive CLI (`input()` prompts) — reviewer sees generated text, underlying evidence summary, and makes a decision
- **Version 1 extension**: Web UI with side-by-side evidence + generated text view

---

## I. Report Generation Workflow

### End-to-End Pipeline

```
Dataset (.xlsx/.csv)
    │
    ▼
[1] LOAD & VALIDATE ─── Schema check, type validation
    │
    ▼
[2] DEDUPLICATE ─── Latest version per safetyreportid → 1,024 cases
    │
    ▼
[3] ANALYZE ─── Run all deterministic analysis modules
    │               Each produces an AnalysisResult
    │
    ▼
[4] ASSEMBLE EVIDENCE ─── For each section, select relevant AnalysisResults
    │                      Build EvidencePacket per section
    │
    ▼
[5] GENERATE SECTIONS ─── For each section:
    │                        - Load section-specific prompt template
    │                        - Inject evidence packet
    │                        - Call LLM
    │                        - Basic grounding check
    │
    ▼
[6] HUMAN REVIEW ─── Interactive section-by-section review
    │                  approve / flag / reject / regenerate
    │
    ▼
[7] ASSEMBLE REPORT ─── Combine approved/flagged sections
    │                     Add metadata: product, period, generation date
    │
    ▼
[8] RENDER ─── Output as Markdown (primary) + optional HTML
    │
    ▼
Final Report (report_output/pader_bisoprolol.md)
```

### Section Order (PADER)
1. Title / Reporting Period
2. Narrative Summary and Analysis
3. Summary Analysis of Cases
4. Reaction / Adverse Event Analysis
5. Serious Cases / 15-Day Alerts
6. Trends and Important Observations
7. History of Actions
8. Case Index / Listing (deterministic, no LLM)

### LLM Usage Rules
- **Sections 1, 8**: Fully deterministic (template fill + data tables). No LLM.
- **Sections 2–6**: LLM generates prose from evidence packets. Each call scoped to ONE section.
- **Section 7**: Deterministic statement: "No history of actions data was supplied for this reporting period."
- **Never**: LLM does arithmetic. LLM sees raw CSV. LLM invents data.

---

## J. Testing Strategy

### J1. Unit Tests

| Test File | What It Tests |
|---|---|
| `test_loader.py` | Excel/CSV loading, schema validation, error handling for missing columns |
| `test_deduplication.py` | Correct case count (1,024), latest version selection, edge cases |
| `test_analysis_modules.py` | Each analysis module's arithmetic: totals, percentages, age bucketing, PT explosion |
| `test_evidence_assembly.py` | Correct evidence packet construction per section, no missing required fields |
| `test_grounding.py` | Every number in generated text traceable to evidence packet |
| `test_report_assembly.py` | All sections present, correct ordering, metadata included |

### J2. Key Test Cases

```python
# Deduplication
def test_unique_case_count():
    """Must produce exactly 1,024 unique cases."""
    assert len(dedup(df)) == 1024

# Seriousness
def test_serious_count():
    """1,023 serious, 1 non-serious."""
    result = case_overview(dedup(df))
    assert result['serious_cases'] == 1023
    assert result['non_serious_cases'] == 1

# Reaction explosion
def test_reaction_count():
    """Deduplicated cases yield 3,429 total reaction instances."""
    reactions = explode_reactions(dedup(df))
    assert len(reactions) == 3429

# Grounding check
def test_numbers_in_text_match_evidence():
    """Any number in generated text must appear in the evidence packet."""
    # Extract all numbers from generated text
    # Verify each appears in evidence_packet.figures
```

### J3. Integration Test
- Full pipeline run with the actual dataset
- Verify output report exists, has all 8 sections, contains expected key figures

### J4. Grounding / Hallucination Check
- Extract all numeric claims from LLM-generated sections
- Cross-reference against the evidence packet that was provided to the LLM
- Flag any number not present in evidence

---

## K. README Contents

The README.md must answer these questions (per Submission Guide):

1. **How to run it** — setup, dependencies, one command to regenerate the report
2. **Architecture** — matches the diagram; data flow, AI vs deterministic split
3. **Where AI is used vs. deterministic code, and why**
4. **Actual prompts/context templates** — shown, not just described
5. **How the system stays grounded** — evidence packets, grounding checks
6. **How to evaluate at scale** — automated grounding verification, numerical consistency
7. **Known limitations** — explicit and honest

### Specific Sections to Include
- Quick Start (setup + run)
- Architecture Overview (refer to diagram)
- Design Decisions (why this split, why no agents/RAG, why per-section LLM calls)
- AI vs Deterministic Boundary
- Prompt Design (link to prompts/ directory + explain template structure)
- Evidence Model (how data flows from Python to LLM)
- Human Review (how it works, what a reviewer sees)
- Grounding Strategy
- Evaluation at Scale
- Known Limitations
- Version 1 Strategy

---

## L. Version 1 Extension Strategy

### Core Principle: Configuration Over Code

Version 0 hardcodes the PADER structure. Version 1 makes report types **declarative**:

```python
# report_types/pader.py → becomes report_types/pader.yaml
report_type: PADER
product: Bisoprolol
sections:
  - id: narrative_summary
    title: "Narrative Summary and Analysis"
    analyses_required: [case_overview, demographics, reactions, seriousness, outcomes]
    prompt_template: prompts/narrative_summary.md
    generation_mode: llm    # vs "deterministic" or "template"
  - id: case_listing
    title: "Case Index / Listing"
    analyses_required: [case_listing]
    generation_mode: deterministic
```

### V1 Features (prioritized)
1. **Section dependency declarations** — each section declares its required analyses
2. **Configurable prompt templates per report type** — PADER prompts ≠ PSUR prompts
3. **Reusable analysis registry** — `case_overview` serves PADER, PSUR, PBRER
4. **Versioned evidence snapshots** — record which dataset + analysis + prompt + model produced each report
5. **Evidence tracing** — annotate generated sentences with source evidence references
6. **Automated evaluation** — compare generated report against golden evidence, score consistency

### Architecture Changes for V1
```
report_types/
├── pader.yaml       # Section list, analyses, prompts
├── psur.yaml        # Different sections, overlapping analyses
└── pbrer.yaml       # Yet another structure

analysis/
├── registry.py      # Register analyses; sections request them by name
└── ...              # Same modules, now registered

evidence/
├── tracer.py        # Annotate each evidence field with its source analysis + line
```

### What Survives from V0
- All analysis modules (reused across report types)
- Evidence model and serialization
- LLM client and section generator
- Human review workflow
- Report renderer
- Grounding checker

### What Changes in V1
- Report structure moves from code to configuration
- Section-analysis coupling becomes declarative
- Prompt templates are loaded from per-report-type directories
- Evidence packets gain tracing metadata

---

## Assumptions and Limitations

### Assumptions
1. **LLM API available**: System requires an LLM API (OpenAI, Anthropic, or similar). API key provided via `.env`.
2. **Single product, single period**: Version 0 handles one product (Bisoprolol) and one reporting period.
3. **English only**: All report output in English.
4. **No MedDRA hierarchy**: Without a SOC mapping table, analysis stays at PT level.
5. **No cumulative data**: This is treated as the first reporting period (no prior data).
6. **No CCDS/label**: Expectedness cannot be determined. Safety Section omitted or marked N/A.
7. **Narratives are stubs**: The `patient_summary_narrativeincludeclinical` field contains only date stubs, not usable clinical narratives. Case presentation sections will be derived from structured fields only.
8. **Deduplication by latest version**: For duplicate `safetyreportid`, the row with the highest `safetyreportversion` is kept.
9. **Country normalization**: "eu" treated as a valid geographic unit (not mapped to individual countries). ISO 2-letter codes normalized to full names where possible.
10. **Age bucketing**: Uses WHO/ICH age groups: Neonate (0–27d), Infant (28d–23mo), Child (2–11y), Adolescent (12–17y), Adult (18–64y), Elderly (≥65y).

### Limitations
1. **No SOC grouping**: The sample report tabulates by System Organ Class, but the dataset lacks an SOC field. Our report uses only Preferred Terms.
2. **No expectedness assessment**: Without a product label/CCDS, we cannot classify reactions as labelled/unlabelled.
3. **No real clinical narratives**: Case presentation will summarize structured data, not clinical narratives.
4. **No exposure data**: Cannot compute incidence rates (no denominator — patient-years of exposure unknown).
5. **No signal detection**: No formal signal detection algorithms (PRR, ROR) — out of scope for V0.
6. **No previous period comparison**: Cumulative and trend-vs-prior-period analysis not possible.
7. **Single LLM dependency**: The prototype depends on one LLM provider; failover not implemented in V0.
8. **CLI-only review**: Human review is via terminal prompts, not a GUI.
9. **Bisoprolol as concomitant**: In 65% of cases, Bisoprolol is a concomitant drug, not the suspect. The report must be transparent about this.
10. **Drug characterization counts discrepancy**: The sample report's reaction count (3,648) includes duplicate case versions. Our system uses 3,429 from deduplicated cases.

---

## Phase 2: What to Implement

Phase 2 (the next step after this plan is approved) should implement the **entire Version 0 prototype** in this exact order:

### Step 1: Project Setup
- Create folder structure, `requirements.txt`, `.env.example`, `config.py`
- Initialize git

### Step 2: Data Ingestion
- `src/ingestion/loader.py` — load Excel/CSV, schema validation
- `src/ingestion/deduplicator.py` — case deduplication
- `tests/test_loader.py`, `tests/test_deduplication.py`

### Step 3: Analysis Modules
- All 7 analysis modules in `src/analysis/`
- `tests/test_analysis_modules.py` with hard-coded expected values

### Step 4: Evidence Model & Assembly
- `src/evidence/model.py` — dataclasses
- `src/evidence/assembler.py` — build packets per section
- `tests/test_evidence_assembly.py`

### Step 5: Prompt Templates
- All 8 section prompts in `prompts/`
- System prompt in `prompts/system.md`

### Step 6: LLM Integration
- `src/generation/llm_client.py` — API wrapper
- `src/generation/section_generator.py` — per-section generation
- `src/generation/grounding_checker.py` — verify claims

### Step 7: Human Review
- `src/review/reviewer.py` — CLI review workflow

### Step 8: Report Assembly & Rendering
- `src/report/assembler.py` + `src/report/renderer.py`
- Generate the actual PADER report for Bisoprolol

### Step 9: Documentation
- `README.md` — complete
- `architecture.md` — Mermaid diagram
- `version1/design.md` — V1 extension strategy

### Step 10: Final Validation
- Run full pipeline end-to-end
- Run all tests
- Verify report output against known data points
