"""
Review Manager: State management, multi-version audit logging, and finalization gating
for the Human-in-the-Loop review system.

Enforces the strict regulatory state machine:
PENDING -> HUMAN REVIEW -> APPROVED (Finalizable)
                        -> FLAGGED / REJECTED -> REGENERATION -> PENDING (Must review again)

Prevents any report from becoming final without explicit human approval for every section.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Any, Literal

from src.config import REPORT_OUTPUT_DIR


def compute_sha256(text: str) -> str:
    """Compute truncated SHA-256 hash for audit verification."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class FinalizationBlockedError(Exception):
    """Raised when final report generation is attempted without complete human approval."""
    def __init__(self, blockers: list[str]):
        self.blockers = blockers
        msg = f"Final report blocked by {len(blockers)} unapproved or non-compliant section(s):\n" + "\n".join(f"  - {b}" for b in blockers)
        super().__init__(msg)


@dataclass
class VersionAuditEntry:
    """Historical audit snapshot for a previous section generation."""
    generation_version: int
    generated_text_hash: str
    evidence_hash: str
    grounding_status: str
    grounding_score: float
    human_status: str
    reviewer: str
    reviewer_comment: str | None
    timestamp: str


@dataclass
class HumanReviewRecord:
    """Single human review decision entry for one section with full version history."""
    section_id: str
    section_title: str
    status: Literal["PENDING", "APPROVED", "FLAGGED"] = "PENDING"
    decision: str = "pending"  # approve | flag | regenerate
    reviewer_comment: str | None = None
    reviewer: str = "Safety Reviewer"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence_hash: str = ""
    generated_text_hash: str = ""
    generation_version: int = 1
    grounding_status: Literal["PASS", "FLAGGED"] = "PASS"
    grounding_score: float = 1.0
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HumanReviewSession:
    """Manages the full review lifecycle and audit trail across all PADER report sections."""

    REQUIRED_SECTIONS = [
        "reporting_period",
        "narrative_summary",
        "case_summary",
        "reaction_analysis",
        "serious_cases",
        "trends",
        "history_of_actions",
        "case_listing",
    ]

    def __init__(self, session_file: str | Path | None = None):
        self.session_file = Path(session_file or (REPORT_OUTPUT_DIR / "review_session.json"))
        self.records: dict[str, HumanReviewRecord] = {}
        self.started_at: str = datetime.now(timezone.utc).isoformat()
        self.load()

    def init_sections(self, section_metadata: list[dict[str, str]]):
        """Initialize records for all sections if not already present."""
        for item in section_metadata:
            sid = item["id"]
            title = item.get("title", sid)
            if sid not in self.records:
                self.records[sid] = HumanReviewRecord(
                    section_id=sid,
                    section_title=title,
                    status="PENDING",
                    decision="pending",
                    generation_version=1
                )
        self.save()

    def approve_section(
        self,
        section_id: str,
        section_title: str,
        comment: str = "Approved as compliant",
        reviewer: str = "Safety Reviewer",
        evidence_text: str = "",
        generated_text: str = "",
        grounding_score: float = 1.0,
    ) -> HumanReviewRecord:
        """
        Record explicit human approval for a section.
        Transitions state to APPROVED.
        """
        rec = self.records.get(section_id)
        current_version = rec.generation_version if rec else 1
        history = list(rec.history) if rec else []

        # Archive current state in history before updating
        if rec and rec.status != "PENDING":
            history.append({
                "generation_version": rec.generation_version,
                "generated_text_hash": rec.generated_text_hash,
                "evidence_hash": rec.evidence_hash,
                "grounding_status": rec.grounding_status,
                "grounding_score": rec.grounding_score,
                "human_status": rec.status,
                "reviewer": rec.reviewer,
                "reviewer_comment": rec.reviewer_comment,
                "timestamp": rec.timestamp
            })

        new_rec = HumanReviewRecord(
            section_id=section_id,
            section_title=section_title,
            status="APPROVED",
            decision="approve",
            reviewer_comment=comment,
            reviewer=reviewer,
            timestamp=datetime.now(timezone.utc).isoformat(),
            evidence_hash=compute_sha256(evidence_text) if evidence_text else "",
            generated_text_hash=compute_sha256(generated_text) if generated_text else "",
            generation_version=current_version,
            grounding_status="PASS" if grounding_score >= 0.80 else "FLAGGED",
            grounding_score=grounding_score,
            history=history
        )
        self.records[section_id] = new_rec
        self.save()
        return new_rec

    def flag_section(
        self,
        section_id: str,
        section_title: str,
        comment: str,
        reviewer: str = "Safety Reviewer",
        evidence_text: str = "",
        generated_text: str = "",
        grounding_score: float = 1.0,
    ) -> HumanReviewRecord:
        """
        Record a human rejection/flag for a section.
        Requires a reason and transitions state to FLAGGED.
        """
        if not comment or not comment.strip():
            raise ValueError("A comment/reason is required when flagging a section.")

        rec = self.records.get(section_id)
        current_version = rec.generation_version if rec else 1
        history = list(rec.history) if rec else []

        if rec:
            history.append({
                "generation_version": rec.generation_version,
                "generated_text_hash": rec.generated_text_hash,
                "evidence_hash": rec.evidence_hash,
                "grounding_status": rec.grounding_status,
                "grounding_score": rec.grounding_score,
                "human_status": rec.status,
                "reviewer": rec.reviewer,
                "reviewer_comment": rec.reviewer_comment,
                "timestamp": rec.timestamp
            })

        new_rec = HumanReviewRecord(
            section_id=section_id,
            section_title=section_title,
            status="FLAGGED",
            decision="flag",
            reviewer_comment=comment.strip(),
            reviewer=reviewer,
            timestamp=datetime.now(timezone.utc).isoformat(),
            evidence_hash=compute_sha256(evidence_text) if evidence_text else "",
            generated_text_hash=compute_sha256(generated_text) if generated_text else "",
            generation_version=current_version,
            grounding_status="FLAGGED" if grounding_score < 0.80 else "PASS",
            grounding_score=grounding_score,
            history=history
        )
        self.records[section_id] = new_rec
        self.save()
        return new_rec

    def record_regeneration(
        self,
        section_id: str,
        section_title: str,
        new_generated_text: str,
        new_evidence_text: str = "",
        new_grounding_score: float = 1.0,
        reviewer: str = "Safety Reviewer",
        comment: str = "Section regenerated"
    ) -> HumanReviewRecord:
        """
        Record regeneration of a section.
        Increments generation version, archives previous state, and RESETS status to PENDING.
        Must be reviewed again by human.
        """
        rec = self.records.get(section_id)
        history = list(rec.history) if rec else []
        old_version = rec.generation_version if rec else 1

        if rec:
            history.append({
                "generation_version": rec.generation_version,
                "generated_text_hash": rec.generated_text_hash,
                "evidence_hash": rec.evidence_hash,
                "grounding_status": rec.grounding_status,
                "grounding_score": rec.grounding_score,
                "human_status": rec.status,
                "reviewer": rec.reviewer,
                "reviewer_comment": rec.reviewer_comment,
                "timestamp": rec.timestamp
            })

        new_version = old_version + 1
        new_rec = HumanReviewRecord(
            section_id=section_id,
            section_title=section_title,
            status="PENDING",  # Strictly reset to PENDING
            decision="regenerate",
            reviewer_comment=comment,
            reviewer=reviewer,
            timestamp=datetime.now(timezone.utc).isoformat(),
            evidence_hash=compute_sha256(new_evidence_text) if new_evidence_text else "",
            generated_text_hash=compute_sha256(new_generated_text) if new_generated_text else "",
            generation_version=new_version,
            grounding_status="PASS" if new_grounding_score >= 0.80 else "FLAGGED",
            grounding_score=new_grounding_score,
            history=history
        )
        self.records[section_id] = new_rec
        self.save()
        return new_rec

    def record_decision(
        self,
        section_id: str,
        section_title: str,
        decision: Literal["approve", "flag", "regenerate"],
        comment: str | None = None,
        reviewer: str = "Safety Reviewer",
        evidence_text: str = "",
        generated_text: str = "",
        generation_version: int = 1,
        grounding_score: float = 1.0
    ) -> HumanReviewRecord:
        """Backwards-compatible wrapper routing to explicit state transition methods."""
        if decision == "approve":
            return self.approve_section(
                section_id, section_title, comment or "Approved", reviewer,
                evidence_text, generated_text, grounding_score
            )
        elif decision == "flag":
            return self.flag_section(
                section_id, section_title, comment or "Flagged by reviewer", reviewer,
                evidence_text, generated_text, grounding_score
            )
        else:
            return self.record_regeneration(
                section_id, section_title, generated_text, evidence_text,
                grounding_score, reviewer, comment or "Regenerated"
            )

    def can_finalize(self, required_sections: list[str] | None = None) -> tuple[bool, list[str]]:
        """
        Hard gatekeeper check for report finalization.
        
        Returns:
            (is_finalizable, list_of_blockers)
        """
        required = required_sections or self.REQUIRED_SECTIONS
        blockers = []

        for sid in required:
            rec = self.records.get(sid)
            if not rec:
                blockers.append(f"Section '{sid}' is missing from review session.")
                continue

            if rec.status == "PENDING":
                blockers.append(f"Section '{rec.section_title}' is PENDING human review.")
            elif rec.status == "FLAGGED":
                reason_suffix = f" (Reason: {rec.reviewer_comment})" if rec.reviewer_comment else ""
                blockers.append(f"Section '{rec.section_title}' is FLAGGED by reviewer{reason_suffix}. Must be regenerated and approved.")
            elif rec.status != "APPROVED":
                blockers.append(f"Section '{rec.section_title}' has invalid status '{rec.status}'.")

        is_allowed = (len(blockers) == 0)
        return is_allowed, blockers

    def is_all_approved(self) -> bool:
        """Return True only if every required section exists and is APPROVED."""
        allowed, _ = self.can_finalize()
        return allowed

    def get_flagged_sections(self) -> list[HumanReviewRecord]:
        """Return all sections currently marked as FLAGGED."""
        return [r for r in self.records.values() if r.status == "FLAGGED"]

    def get_pending_sections(self) -> list[HumanReviewRecord]:
        """Return all sections currently PENDING review."""
        return [r for r in self.records.values() if r.status == "PENDING"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "all_approved": self.is_all_approved(),
            "total_sections": len(self.records),
            "approved_count": sum(1 for r in self.records.values() if r.status == "APPROVED"),
            "flagged_count": sum(1 for r in self.records.values() if r.status == "FLAGGED"),
            "pending_count": sum(1 for r in self.records.values() if r.status == "PENDING"),
            "sections": {sid: r.to_dict() for sid, r in self.records.items()}
        }

    def save(self):
        """Persist session state to disk."""
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.session_file.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def load(self):
        """Load session state from disk if exists."""
        if self.session_file.exists():
            try:
                data = json.loads(self.session_file.read_text(encoding="utf-8"))
                self.started_at = data.get("started_at", self.started_at)
                for sid, rdict in data.get("sections", {}).items():
                    self.records[sid] = HumanReviewRecord(**rdict)
            except Exception:
                pass
