"""
Grounding Validator: Rigorous compliance verification and hallucination detection.

Audits every generated claim against the section's approved evidence packet.
Flags unsupported numbers, contradictory metrics, invented regulatory actions,
unsupported causal conclusions, expectedness assertions, and SOC claims.
"""
from __future__ import annotations

import re
import json
from typing import Any
from src.generation_models import SectionEvidencePacket, GroundedClaim, GeneratedSectionOutput


# Forbidden terms / unsupported concepts for this dataset
FORBIDDEN_CONCEPTS = {
    "soc_inference": [
        r"\bBlood and lymphatic system disorders\b",
        r"\bCardiac disorders SOC\b",
        r"\bGeneral disorders and administration site conditions\b",
        r"\bclassified under (?:the )?[A-Za-z ]+ SOC\b",
    ],
    "causal_claims": [
        r"\bconfirms? (?:a )?causal (?:relationship|link)\b",
        r"\bproves? that bisoprolol caused\b",
        r"\bdefinitive (?:safety )?signal\b",
        r"\bconfirmed emerging signal\b",
    ],
    "invented_actions": [
        r"\blabel(?:ing)? (?:was|has been) (?:updated|revised|amended)\b",
        r"\bblack box warning (?:added|mandated)\b",
        r"\brecall (?:was|initiated)\b",
        r"\brisk management plan (?:implemented|revised)\b",
    ],
    "unsupported_expectedness": [
        r"\bclassified as (?:unlabelled|unlabeled)\b",
        r"\bclassified as (?:labelled|labeled)\b",
        r"\bexpectedness was determined to be\b",
    ],
}


def extract_all_numbers(text: str) -> set[str]:
    """
    Extract numbers, floats, percentages, and comma-formatted integers from text.
    Strips dates (YYYY-MM-DD), regulation citations (e.g. 21 CFR 314.80), and section numbers.
    """
    # Remove dates like 2024-12-27, 2025-12-26
    cleaned = re.sub(r'\b\d{4}[-/]\d{2}[-/]\d{2}\b', ' ', text)
    # Remove CFR citations like 21 CFR 314.80
    cleaned = re.sub(r'\b21\s+CFR\s+314\.80\b', ' ', cleaned, flags=re.IGNORECASE)
    # Remove table/section headers like 'Table 1', 'Table 8', '## 1.', '## 2.'
    cleaned = re.sub(r'\b(?:Table|Section|##)\s+\d+\b', ' ', cleaned, flags=re.IGNORECASE)

    pattern = r'\b(\d+(?:,\d{3})*(?:\.\d+)?%?)\b'
    matches = re.findall(pattern, cleaned)
    filtered = set()

    for m in matches:
        clean = m.replace(",", "").replace("%", "").strip()
        try:
            val = float(clean)
            if val == 0:
                continue
            # Skip calendar years
            if val in (2024, 2025, 2026) and not ("%" in m or "," in m):
                continue
            filtered.add(m)
        except ValueError:
            continue

    return filtered

    return filtered


def normalize_num_str(num_str: str) -> str:
    """Normalize a numerical string for set membership comparison."""
    clean = num_str.replace(",", "").replace("%", "").strip()
    try:
        val = float(clean)
        if val == int(val):
            return str(int(val))
        return f"{val:.2f}".rstrip("0").rstrip(".")
    except ValueError:
        return clean


def flatten_evidence_numbers(data: Any) -> set[str]:
    """Recursively collect all numeric strings and floats from evidence dictionary."""
    collected = set()
    if isinstance(data, dict):
        for k, v in data.items():
            collected.update(flatten_evidence_numbers(v))
    elif isinstance(data, list):
        for item in data:
            collected.update(flatten_evidence_numbers(item))
    elif isinstance(data, (int, float)):
        collected.add(str(data))
        collected.add(normalize_num_str(str(data)))
    elif isinstance(data, str):
        # Extract embedded numbers in strings
        for n in extract_all_numbers(data):
            collected.add(n)
            collected.add(normalize_num_str(n))
    return collected


def validate_generated_section(
    section_id: str,
    generated_text: str,
    evidence_packet: SectionEvidencePacket,
    claims: list[GroundedClaim] | None = None
) -> GeneratedSectionOutput:
    """
    Audit generated section text and claims against approved evidence.

    Returns:
        GeneratedSectionOutput with populated claims, grounding score, and warnings.
    """
    warnings: list[str] = []
    processed_claims: list[GroundedClaim] = claims or []

    # 1. Flatten all approved numbers in evidence
    approved_numbers = flatten_evidence_numbers(evidence_packet.approved_metrics)
    normalized_approved = {normalize_num_str(n) for n in approved_numbers}

    # 2. Extract numbers in generated text
    text_numbers = extract_all_numbers(generated_text)
    ungrounded_numbers = []

    for num in text_numbers:
        norm_num = normalize_num_str(num)
        if norm_num not in normalized_approved and num not in approved_numbers:
            ungrounded_numbers.append(num)

    if ungrounded_numbers:
        warnings.append(f"Ungrounded numerical figures detected: {sorted(set(ungrounded_numbers))[:8]}")

    # 3. Check for Forbidden / Unsupported Concepts
    for concept, patterns in FORBIDDEN_CONCEPTS.items():
        for pat in patterns:
            match = re.search(pat, generated_text, re.IGNORECASE)
            if match:
                msg = f"Violation of grounding constraint [{concept}]: '{match.group(0)}' detected in generated text."
                warnings.append(msg)

    # 4. Process and Audit Claims
    if not processed_claims:
        units = []
        for line in generated_text.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith("#") or line_str.startswith("|---"):
                continue
            if line_str.startswith("|") and line_str.endswith("|"):
                # Markdown table row
                units.append(line_str)
            else:
                # Prose line: split into sentences
                for s in re.split(r'(?<=[.!?])\s+', line_str):
                    if len(s.strip()) > 10:
                        units.append(s.strip())

        for u in units:
            u_nums = extract_all_numbers(u)
            u_ungrounded = [n for n in u_nums if normalize_num_str(n) not in normalized_approved]

            # Check concept violations in sentence
            u_violations = []
            for concept, patterns in FORBIDDEN_CONCEPTS.items():
                for pat in patterns:
                    if re.search(pat, u, re.IGNORECASE):
                        u_violations.append(concept)

            if u_ungrounded or u_violations:
                reasons = []
                if u_ungrounded:
                    reasons.append(f"unsupported numbers {u_ungrounded}")
                if u_violations:
                    reasons.append(f"forbidden concepts {u_violations}")
                processed_claims.append(GroundedClaim(
                    claim_text=u,
                    extracted_figures=list(u_nums),
                    status="FLAGGED",
                    flag_reason="; ".join(reasons)
                ))
            else:
                processed_claims.append(GroundedClaim(
                    claim_text=u,
                    extracted_figures=list(u_nums),
                    status="VERIFIED",
                    evidence_id=f"{section_id}.metric"
                ))

    # Calculate Grounding Score
    total_claims = len(processed_claims)
    verified_claims = sum(1 for c in processed_claims if c.status == "VERIFIED")
    grounding_score = round(verified_claims / total_claims, 3) if total_claims > 0 else 1.0

    # Extract all evidence_ids used
    evidence_ids = [c.evidence_id for c in processed_claims if c.evidence_id]

    return GeneratedSectionOutput(
        section_name=evidence_packet.section_title,
        generated_text=generated_text,
        claims=processed_claims,
        evidence_ids_used=list(set(evidence_ids)),
        warnings_or_uncertainties=warnings,
        grounding_score=grounding_score,
        generation_mode="llm"
    )
