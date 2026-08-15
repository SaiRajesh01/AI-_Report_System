"""
Central configuration for the PADER report generation system.

Design rationale: All configuration lives here rather than scattered across modules.
Report-type-specific configuration is in src/report_types/.
"""
from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

# ─── Paths ───────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT
PROMPTS_DIR = PROJECT_ROOT / "prompts"
REPORT_OUTPUT_DIR = PROJECT_ROOT / "report_output"

# ─── Dataset ─────────────────────────────────────────────────────────────────

DATASET_FILENAME = os.getenv("DATASET_PATH", "Bisoprolol_icsr_sample_1068rows.xlsx")
DATASET_PATH = DATA_DIR / DATASET_FILENAME

# ─── LLM ─────────────────────────────────────────────────────────────────────

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Temperature for report generation — low for consistency
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))

# ─── Product ─────────────────────────────────────────────────────────────────

PRODUCT_NAME = "Bisoprolol"
APPLICATION_NUMBER = "B-1"
COMPANY_NAME = "Dev Pharma Client"

# ─── Schema ──────────────────────────────────────────────────────────────────

# Required columns that must exist in the dataset
REQUIRED_COLUMNS = [
    "safetyreportid",
    "safetyreportversion",
    "serious",
    "receivedate",
    "patient_patientsex",
    "patient_patientonsetage",
    "patient_patientonsetageunit",
    "patient_reaction_reactionmeddrapt",
    "patient_reaction_reactionoutcome",
    "patient_drug_drugcharacterization",
    "patient_drug_medicinalproduct",
    "primarysourcecountry",
    "primarysource_qualification",
    "reporttype",
    "fulfillexpeditecriteria",
    "seriousnessdeath",
    "seriousnesslifethreatening",
    "seriousnesshospitalization",
    "seriousnessdisabling",
    "seriousnesscongenitalanomali",
    "seriousnessother",
]

# ─── Age Groups (ICH/WHO standard) ──────────────────────────────────────────

AGE_GROUP_BINS = [0, 1/12, 2, 12, 18, 65, 200]  # in years
AGE_GROUP_LABELS = ["Neonate", "Infant/Toddler", "Child", "Adolescent", "Adult", "Elderly"]

# ─── Country Normalization ───────────────────────────────────────────────────

COUNTRY_CODE_MAP = {
    "IE": "Ireland",
    "RO": "Romania",
    "SA": "Saudi Arabia",
    "UA": "Ukraine",
    "HR": "Croatia",
    "FI": "Finland",
}

# ─── Analysis ────────────────────────────────────────────────────────────────

TOP_N_REACTIONS = 20  # Number of top PTs to include in analysis
TOP_N_DRUGS = 10      # Number of top concomitant drugs to show
