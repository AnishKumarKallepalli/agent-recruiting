"""Dashboard API — simple endpoints to feed the live status view."""
from fastapi import APIRouter
import db

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/roles/{role_id}/status")
def role_status(role_id: str):
    """Full workflow status for a role — used by the dashboard."""
    role = db.get_role(role_id)
    candidates = db.get_candidates_for_role(role_id)

    calls = db.get_db().table("calls").select("*").eq("role_id", role_id).execute().data
    emails = db.get_db().table("emails").select("*").eq("role_id", role_id).execute().data

    return {
        "role": role,
        "candidates": candidates,
        "calls": calls,
        "emails": emails,
        "summary": {
            "role_created": role is not None,
            "candidates_sourced": len(candidates),
            "calls_made": len([c for c in calls if c["call_type"] == "screening"]),
            "qualified": len([c for c in candidates if c["status"] == "qualified"]),
            "emails_sent": len(emails),
        },
    }


@router.get("/roles")
def list_roles():
    db_ = db.get_db()
    roles = db_.table("roles").select("*").order("created_at", desc=True).execute().data
    return {"roles": roles}


@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: str):
    db_ = db.get_db()
    candidate = db_.table("candidates").select("*").eq("id", candidate_id).single().execute().data
    calls = db_.table("calls").select("*").eq("candidate_id", candidate_id).execute().data
    emails = db_.table("emails").select("*").eq("candidate_id", candidate_id).execute().data
    return {"candidate": candidate, "calls": calls, "emails": emails}
