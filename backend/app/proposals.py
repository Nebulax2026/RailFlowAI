from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.audit import record_audit_event
from app.domain.enums import ScheduleOption
from app.domain.models import ProposalSnapshot, ScheduleAlternative
from app.repositories import proposal_snapshot_repository, unit_of_work


def record_proposal_snapshot(request_ids: list[str], alternatives: list[ScheduleAlternative]) -> ProposalSnapshot:
    snapshot = ProposalSnapshot(
        proposal_id=f"proposal-{uuid4().hex}",
        request_ids=request_ids,
        alternatives=alternatives,
        created_at=datetime.now(timezone.utc),
    )
    with unit_of_work() as work:
        saved = work.proposals.save(snapshot)
        record_audit_event(
            "proposal_generated",
            f"Generated {len(alternatives)} proposal option{'' if len(alternatives) == 1 else 's'}.",
            actor="system",
            request_ids=request_ids,
            proposal_id=saved.proposal_id,
            details={
                "options": [alternative.option.value for alternative in alternatives],
                "overall_scores": [alternative.overall_score for alternative in alternatives],
            },
        )
    return snapshot


def mark_proposal_applied(
    proposal_id: str | None,
    request_ids: list[str],
    option: ScheduleOption,
    applied_by: str,
) -> ProposalSnapshot | None:
    snapshot = proposal_snapshot_repository.get(proposal_id) if proposal_id else None
    if not snapshot:
        snapshot = proposal_snapshot_repository.latest_generated_for(request_ids, option)
    if not snapshot:
        return None

    applied = snapshot.model_copy(
        update={
            "status": "applied",
            "selected_option": option,
            "applied_at": datetime.now(timezone.utc),
            "applied_by": applied_by,
        }
    )
    with unit_of_work() as work:
        work.proposals.save(applied)
        record_audit_event(
            "proposal_applied",
            f"Applied proposal {applied.proposal_id} using {option.value}.",
            actor=applied_by,
            request_ids=applied.request_ids,
            proposal_id=applied.proposal_id,
            details={"selected_option": option.value},
        )
    return applied
