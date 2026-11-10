"""Fail-closed validation of *manual* QB starter confirmations for future shadow captures.

A URL and timestamp alone DO NOT prove who is starting. A row can be promoted
to 'verified_pregame' only if an operator independently reviewed game-specific
source CONTENT, recorded the confirmation scope, and timestamped that review
before kickoff. This module validates the attestation's metadata; it cannot
verify the truth of the source content itself.

Rows without complete evidence are excluded from overrides, not converted into
verified starters. The QB engine then labels its fallback 'provisional'.
"""
from __future__ import annotations

import pandas as pd

from research.audit_qb_starter_source_metadata import audit, kickoff_utc

REQUIRED_FIELDS={
    "game_id", "team", "qb_id", "qb_name", "source_url",
    "source_published_at_utc", "source_checked_at_utc",
    "source_reviewed", "confirmation_kind", "review_note",
}
ELIGIBLE_KINDS={
    "coach_explicitly_names_starting_qb_for_game",
    "team_explicitly_names_starting_qb_for_game",
    "official_pregame_starter_confirmation",
}
MAX_SOURCE_AGE_HOURS=240.0


def _affirmed(value:object)->bool:
    return str(value).strip().lower() in {"true", "yes", "1"}


def validate_starter_confirmations(
    schedule:pd.DataFrame,
    confirmations:pd.DataFrame,
    *,
    checked_as_of_utc=None,
)->tuple[pd.DataFrame,pd.DataFrame]:
    """Return (eligible overrides, row-level audit); never assume confirmation.

    'source_checked_at_utc' represents *when the source content was actually
    reviewed*, not when this Python job runs. A reviewed row still only means
    its author attests the source confirms this specific game.
    """
    missing=REQUIRED_FIELDS-set(confirmations.columns)
    if missing:
        raise ValueError(f"QB starter confirmations missing required evidence fields: {sorted(missing)}")
    if confirmations.duplicated(["game_id","team"]).any():
        raise ValueError("Duplicate starter confirmation for game/team")
    now=pd.Timestamp.now(tz="UTC") if checked_as_of_utc is None else pd.to_datetime(
        checked_as_of_utc,errors="coerce",utc=True
    )
    if pd.isna(now):
        raise ValueError("Current UTC evaluation timestamp is invalid")
    # The existing audit checks all reported game/team identifiers, kickoff
    # timezone conversion, publication date, and HTTPS source provenance.
    metadata=audit(schedule,confirmations,max_age_hours=MAX_SOURCE_AGE_HOURS)
    metadata["source_reviewed"]=False
    metadata["confirmation_kind"]=""
    metadata["source_checked_at_utc"]=""
    metadata["review_note"]=""
    metadata["override_eligible"]=False
    metadata["eligibility_reason"]=""
    for idx,rec in enumerate(confirmations.to_dict("records")):
        problems=[]
        reviewed=_affirmed(rec.get("source_reviewed",""))
        kind=str(rec.get("confirmation_kind","")).strip()
        note=str(rec.get("review_note","")).strip()
        checked=pd.to_datetime(rec.get("source_checked_at_utc"),errors="coerce",utc=True)
        published=pd.to_datetime(rec.get("source_published_at_utc"),errors="coerce",utc=True)
        kickoff=pd.to_datetime(metadata.loc[idx,"kickoff_utc"],errors="coerce",utc=True)
        status=metadata.loc[idx,"metadata_status"]
        if status!="recent_metadata_only_content_unverified":
            problems.append("metadata_not_current_or_invalid")
        if not reviewed:
            problems.append("source_content_not_reviewed")
        if kind not in ELIGIBLE_KINDS:
            problems.append("source_does_not_explicitly_confirm_starter")
        if len(note)<15:
            problems.append("game_specific_review_note_missing")
        if pd.isna(checked):
            problems.append("content_review_timestamp_missing")
        else:
            if checked>now:
                problems.append("content_review_timestamp_in_future")
            if pd.notna(kickoff) and checked>=kickoff:
                problems.append("content_review_at_or_after_kickoff")
            if pd.notna(published) and checked<published:
                problems.append("content_review_before_source_publication")
        metadata.loc[idx,"source_reviewed"]=reviewed
        metadata.loc[idx,"confirmation_kind"]=kind
        metadata.loc[idx,"source_checked_at_utc"]=str(rec.get("source_checked_at_utc",""))
        metadata.loc[idx,"review_note"]=note
        metadata.loc[idx,"override_eligible"]=not problems
        metadata.loc[idx,"eligibility_reason"]=";".join(problems) if problems else "explicit_reviewed_game_starter_confirmation"
    eligible_keys=metadata.loc[metadata.override_eligible,["game_id","team"]]
    if eligible_keys.empty:
        accepted=confirmations.iloc[0:0].copy()
    else:
        accepted=confirmations.merge(eligible_keys,on=["game_id","team"],how="inner",validate="one_to_one")
    return accepted,metadata
