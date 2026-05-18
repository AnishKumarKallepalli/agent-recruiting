"""Dashboard API — simple endpoints to feed the live status view."""
import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from config import settings
import db

FOUNDER_CALL_ID = "cmpah5blp048xjeebqqcki2ln"
ALEX_CALL_ID    = "cmpah1q2c04rl5ipo19ct0dq8"

router = APIRouter(prefix="/api", tags=["dashboard"])


def _recording_response(call_id: str) -> StreamingResponse:
    headers = {"Authorization": f"Bearer {settings.agentphone_api_key}"}
    r = httpx.get(
        f"https://api.agentphone.ai/v1/calls/{call_id}/recording",
        headers=headers,
        timeout=30,
        follow_redirects=True,
    )
    r.raise_for_status()
    return StreamingResponse(
        iter([r.content]),
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/recordings/founder")
def founder_recording():
    return _recording_response(FOUNDER_CALL_ID)


@router.get("/recordings/alex")
def alex_recording():
    return _recording_response(ALEX_CALL_ID)


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
