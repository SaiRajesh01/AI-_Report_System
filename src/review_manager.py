"""
Review Manager: State management and audit logging for the Human-in-the-Loop review system.

Tracks approval states, reviewer comments, evidence cryptographic hashes,
and coordinates non-destructive section flagging and regeneration.
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


@dataclass
class HumanReviewRecord:
    """Single human review decision entry for one section."""
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HumanReviewSession:
    """Manages the full review lifecycle across all 8 PADER report sections."""

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
                    decision="pending"
                )

    def record_decision(
        self,
        section_id: str,
        section_title: str,
        decision: Literal["approve", "flag", "regenerate"],
        comment: str | None = None,
        reviewer: str = "Safety Reviewer",
        evidence_text: str = "",
        generated_text: str = "",
        generation_version: int = 1
    ) -> HumanReviewRecord:
        """Record or update a human review decision for a section."""
        status_map = {
            "approve": "APPROVED",
            "flag": "FLAGGED",
            "regenerate": "PENDING"
        }
        rec = HumanReviewRecord(
            section_id=section_id,
            section_title=section_title,
            status=status_map.get(decision, "PENDING"),
            decision=decision,
            reviewer_comment=comment,
            reviewer=reviewer,
            timestamp=datetime.now(timezone.utc).isoformat(),
            evidence_hash=compute_sha256(evidence_text) if evidence_text else "",
            generated_text_hash=compute_sha256(generated_text) if generated_text else "",
            generation_version=generation_version
        )
        self.records[section_id] = rec
        self.save()
        return rec

    def is_all_approved(self) -> bool:
        """Check if all active sections have been approved."""
        if not self.records:
            return False
        return all(r.status == "APPROVED" for r in self.records.values())

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
