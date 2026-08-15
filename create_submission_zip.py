"""
Submission Packaging Tool: Creates a clean, audited submission ZIP archive meeting all challenge requirements.
"""
from __future__ import annotations

import os
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ZIP_OUTPUT = PROJECT_ROOT / "firstname_lastname_genar_challenge.zip"

EXCLUDE_DIRS = {
    "__pycache__",
    ".pytest_cache",
    "venv",
    ".venv",
    "node_modules",
    ".git",
    ".gemini",
    "tmp",
    ".agents",
}

EXCLUDE_FILES = {
    ".env",
    "Bisoprolol_icsr_sample_1068rows.csv",
    "Bisoprolol_icsr_sample_1068rows.xlsx",
    "completeness_test.md",
    "final_pader_test.md",
    "test_draft_pader.md",
    "pader_bisoprolol_draft.md",
    "pader_bisoprolol.md",
}

EXCLUDE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".DS_Store",
    ".pdf",
    ".zip",
}


def create_submission_zip(output_filename: str = "firstname_lastname_genar_challenge.zip") -> tuple[Path, int, list[str]]:
    """Package project files into a clean submission ZIP."""
    zip_path = PROJECT_ROOT / output_filename
    if zip_path.exists():
        zip_path.unlink()

    packaged_files = []

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(PROJECT_ROOT):
            # Exclude unwanted directories
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]

            for file in files:
                file_path = Path(root) / file
                rel_path = file_path.relative_to(PROJECT_ROOT)
                file_str = str(rel_path).replace("\\", "/")

                # Exclude specific files
                if file in EXCLUDE_FILES or (file.startswith(".env") and file != ".env.example"):
                    continue

                if file.endswith("_test.md"):
                    continue

                # Exclude specific extensions (e.g. .pdf, .zip, .pyc)
                if file_path.suffix.lower() in EXCLUDE_EXTENSIONS:
                    continue

                if any(part in EXCLUDE_DIRS for part in rel_path.parts):
                    continue

                # Add file to archive
                zipf.write(file_path, arcname=file_str)
                packaged_files.append(file_str)

    size_bytes = zip_path.stat().st_size
    return zip_path, size_bytes, packaged_files


if __name__ == "__main__":
    zip_path, size_bytes, files = create_submission_zip()
    size_mb = size_bytes / (1024 * 1024)
    print(f"Submission ZIP created successfully!")
    print(f"Archive: {zip_path.name}")
    print(f"Location: {zip_path}")
    print(f"Size: {size_mb:.2f} MB ({size_bytes:,} bytes)")
    print(f"Total packaged files: {len(files)}")
