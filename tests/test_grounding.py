"""
Tests for canonical grounding validation.
"""
import pytest

from src.grounding_validator import (
    validate_generated_section,
    extract_all_numbers,
    normalize_num_str
)
from src.generation_models import SectionEvidencePacket


@pytest.fixture
def sample_packet():
    return SectionEvidencePacket(
        section_id="narrative_summary",
        section_title="2. Narrative Summary",
        product_name="Bisoprolol",
        reporting_period={"start_date": "2024-12-27", "end_date": "2025-12-26"},
        approved_metrics={
            "total_cases": 1024,
            "serious_cases": 1023,
            "serious_pct": 99.9,
            "fatal_cases": 68,
        },
        metric_catalog=[],
        constraints=["Only use approved metrics."]
    )


class TestGroundingChecker:
    def test_fully_grounded_text(self, sample_packet):
        """Text with only known numbers should pass validation."""
        text = "During the reporting period, 1,024 cases were received, of which 1,023 (99.9%) were serious."
        out = validate_generated_section("narrative_summary", text, sample_packet)
        assert out.grounding_score == 1.0
        assert len(out.warnings_or_uncertainties) == 0

    def test_ungrounded_number(self, sample_packet):
        """Text with a fabricated number should fail validation."""
        text = "During the period, 500 cases were received with 200 deaths."
        out = validate_generated_section("narrative_summary", text, sample_packet)
        assert len(out.warnings_or_uncertainties) > 0
        assert out.grounding_score < 1.0

    def test_empty_text(self, sample_packet):
        """Empty text should pass with 1.0."""
        out = validate_generated_section("narrative_summary", "", sample_packet)
        assert out.grounding_score == 1.0

    def test_extract_numbers(self):
        """Should extract integers, floats, percentages, comma-separated numbers."""
        text = "Received 1,024 cases (99.9% serious), including 68 fatal and 482 hospitalized."
        numbers = extract_all_numbers(text)
        assert "1,024" in numbers or "1024" in numbers
        assert "99.9%" in numbers or "99.9" in numbers
        assert "68" in numbers
        assert "482" in numbers

    def test_normalize_number(self):
        """Should normalize various number formats."""
        assert normalize_num_str("1,024") == "1024"
        assert normalize_num_str("99.9%") == "99.9"
        assert normalize_num_str("01") == "1"
        assert normalize_num_str("70.05") == "70.05"
