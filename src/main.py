"""
Main CLI entry point: orchestrates the full pipeline from dataset to PADER report.

Usage:
    python -m src.main                           # Interactive mode (launches Streamlit or CLI)
    python -m src.main --auto-approve             # Automated generation (CI/Testing)
    python -m src.main --dataset path/to/file.csv # Specify dataset path
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import DATASET_PATH, REPORT_OUTPUT_DIR
from run_pader_pipeline import run_full_pader_pipeline


def main():
    parser = argparse.ArgumentParser(description="GenAR PADER Regulatory Report Pipeline")
    parser.add_argument("--dataset", type=str, default=str(DATASET_PATH), help="Path to ICSR safety dataset")
    parser.add_argument("--auto-approve", action="store_true", help="Auto-approve all sections and generate final report")
    args = parser.parse_args()

    print(f"Executing GenAR PADER pipeline with dataset: {args.dataset}")
    out_docx = run_full_pader_pipeline(args.dataset)
    print(f"\nFinal report generation complete: {out_docx}")


if __name__ == "__main__":
    main()
