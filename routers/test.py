"""
Test endpoints — trigger pipeline without burning real phone credits.

POST /test/intake      → runs full intake pipeline with fake transcript
POST /test/screening   → runs screening summary + email with fake transcript
GET  /test/db          → shows current DB state at a glance
"""
import logging
from fastapi import APIRouter, BackgroundTasks
from routers.webhooks import _process_inbound_intake

router = APIRouter(prefix="/test", tags=["test"])
logger = logging.getLogger(__name__)

# Realistic fake intake transcript — same info as the real call
FAKE_INTAKE_TRANSCRIPT = [
    {"role": "agent", "content": "Hi! I'm Ava, your AI recruiting agent. I'm going to ask you a few quick questions to understand the role you're hiring for, and then I'll take it from there. Sound good?"},
    {"role": "user",  "content": "Sounds good."},
    {"role": "agent", "content": "What role are you looking to hire for?"},
    {"role": "user",  "content": "Founding AI Engineer."},
    {"role": "agent", "content": "Tell me a bit about your company — what do you do?"},
    {"role": "user",  "content": "We're building an AI-powered voice agent startup focused on emotional AI."},
    {"role": "agent", "content": "What are the must-have skills?"},
    {"role": "user",  "content": "Python, LLM experience, backend infra, APIs."},
    {"role": "agent", "content": "Nice-to-haves?"},
    {"role": "user",  "content": "Startup experience, voice AI, good communication."},
    {"role": "agent", "content": "What kind of background are you looking for?"},
    {"role": "user",  "content": "Someone who has worked at small AI startups, not big tech."},
    {"role": "agent", "content": "Location?"},
    {"role": "user",  "content": "San Francisco, in-person 5 days a week."},
    {"role": "agent", "content": "Compensation range?"},
    {"role": "user",  "content": "Base of $160k to $200k, flexible for great candidates."},
    {"role": "agent", "content": "Any dealbreakers?"},
    {"role": "user",  "content": "No one from Google or big tech companies."},
    {"role": "agent", "content": "Do you have a booking link?"},
    {"role": "user",  "content": "Yes, cal.com/demo."},
    {"role": "agent", "content": "Great — I'll start finding candidates and reach out to the best ones. Talk soon!"},
    {"role": "user",  "content": "Thank you, bye!"},
]


@router.post("/intake")
async def test_intake(background_tasks: BackgroundTasks):
    """
    Simulate a completed founder intake call.
    Runs: Gemini extraction → Supabase writes → candidate loading → outbound call to Alex.
    No phone credits used until the outbound call to Alex fires.
    """
    logger.info("TEST: triggering intake pipeline with fake transcript")
    background_tasks.add_task(
        _process_inbound_intake,
        agentphone_call_id="test-call-" + __import__('uuid').uuid4().hex[:8],
        transcript_raw=FAKE_INTAKE_TRANSCRIPT,
        transcript_str="\n".join(
            f"{t['role'].capitalize()}: {t['content']}"
            for t in FAKE_INTAKE_TRANSCRIPT
        ),
        duration=205,
    )
    return {
        "ok": True,
        "message": "Intake pipeline triggered. Watch railway logs. Outbound call to Alex will fire at the end.",
        "warning": "This WILL make a real outbound call to the candidate's number in data/candidates.json"
    }


@router.post("/intake/no-call")
async def test_intake_no_call(background_tasks: BackgroundTasks):
    """
    Same as /test/intake but stops before the outbound call.
    Use this to test Gemini extraction + Supabase writes only — zero credits.
    """
    import json, os
    from agents import gemini
    import db

    logger.info("TEST: intake pipeline (no outbound call)")

    transcript_str = "\n".join(
        f"{t['role'].capitalize()}: {t['content']}"
        for t in FAKE_INTAKE_TRANSCRIPT
    )

    founder = db.get_or_create_founder(
        name="Test Founder", phone="+10000000001", email="test@demo.com"
    )
    role_row = db.create_role(founder["id"], {"title": "Pending", "raw_transcript": transcript_str})
    role_id = role_row["id"]

    call_row = db.create_call(call_type="intake", role_id=role_id, agentphone_call_id="test-no-call-" + __import__('uuid').uuid4().hex[:8])
    db.update_call(call_row["id"], status="completed", transcript=transcript_str, duration_seconds=205)

    brief = gemini.extract_role_brief(transcript_str)
    brief["id"] = role_id

    db.get_db().table("roles").update({
        "title": brief.get("title"), "company": brief.get("company"),
        "location": brief.get("location"), "must_haves": brief.get("must_haves", []),
        "nice_haves": brief.get("nice_haves", []), "comp_range": brief.get("comp_range"),
        "target_background": brief.get("target_background"),
        "dealbreakers": brief.get("dealbreakers"), "booking_link": brief.get("booking_link"),
        "raw_transcript": transcript_str,
    }).eq("id", role_id).execute()

    candidates_path = os.path.join(os.path.dirname(__file__), "..", "data", "candidates.json")
    with open(candidates_path) as f:
        cached = json.load(f)
    inserted = db.insert_candidates(role_id, cached)

    return {
        "ok": True,
        "role_id": role_id,
        "brief": brief,
        "candidates_loaded": len(inserted),
        "top_candidate": max(inserted, key=lambda c: c.get("fit_score", 0))["name"],
        "credits_used": 0,
    }


@router.get("/db")
async def test_db_state():
    """Quick snapshot of current DB state."""
    db_ = __import__('db').get_db()
    founders  = db_.table("founders").select("id,name,phone").execute().data
    roles     = db_.table("roles").select("id,title,company,status").execute().data
    candidates = db_.table("candidates").select("id,name,fit_score,status").execute().data
    calls     = db_.table("calls").select("id,call_type,status,outcome").execute().data
    emails    = db_.table("emails").select("id,to_email,status").execute().data
    return {
        "founders": founders, "roles": roles,
        "candidates": candidates, "calls": calls, "emails": emails,
    }
