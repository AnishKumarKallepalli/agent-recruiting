"""
Internal endpoints for pipeline simulation and DB inspection.

POST /test/intake      → runs full intake pipeline
POST /test/screening   → runs screening summary + email
GET  /test/db          → shows current DB state at a glance
"""
import logging
from fastapi import APIRouter, BackgroundTasks
from routers.webhooks import _process_inbound_intake

router = APIRouter(prefix="/test", tags=["test"])
logger = logging.getLogger(__name__)

# Sample intake transcript
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
    """Trigger full intake pipeline."""
    logger.info("Triggering intake pipeline")
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
        "message": "Intake pipeline triggered."
    }


@router.post("/intake/no-call")
async def test_intake_no_call(background_tasks: BackgroundTasks):
    """Run intake pipeline through extraction and DB writes only."""
    import json, os
    from agents import gemini
    import db

    logger.info("Intake pipeline (extraction only)")

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


@router.post("/demo/send-followup")
async def demo_send_followup():
    """Send the candidate follow-up email."""
    from services import agentmail

    subject = "Founding AI Engineer @ NovaMind - let's connect"
    body = (
        "Hi Alex,\n\n"
        "Great speaking with you just now! I wanted to follow up on the Founding AI Engineer role at NovaMind.\n\n"
        "Given your background shipping LLM agent infrastructure at Letta and production voice AI pipelines, "
        "you're exactly the profile they're looking for. This is a founding-team seat — high ownership, "
        "real equity, and a chance to shape the architecture from day one.\n\n"
        "Book time directly with the founder here: cal.com/novamind\n\n"
        "Talk soon,\n"
        "Ava (AI recruiting agent)"
    )
    html = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f4ef;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 20px">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e5dfd2">
  <tr><td style="background:#1a1814;padding:24px 32px">
    <div style="font-size:22px;font-weight:700;color:#fff;letter-spacing:-0.02em">Founding AI Engineer</div>
    <div style="font-size:14px;color:rgba(255,255,255,0.55);margin-top:4px">at NovaMind</div>
  </td></tr>
  <tr><td style="padding:32px">
    <p style="margin:0 0 16px;font-size:15px;color:#2c2924">Hi Alex,</p>
    <p style="margin:0 0 16px;font-size:15px;color:#2c2924;line-height:1.6">
      Great speaking with you just now! I wanted to follow up on the <strong>Founding AI Engineer</strong> role at NovaMind.
    </p>
    <p style="margin:0 0 16px;font-size:15px;color:#2c2924;line-height:1.6">
      Your background shipping LLM agent infrastructure at Letta and production voice AI pipelines is exactly what they're looking for.
      This is a founding-team seat — high ownership, real equity, and a chance to shape the architecture from day one.
    </p>
    <div style="background:#f5f4ef;border:1px solid #e5dfd2;border-radius:8px;padding:18px 20px;margin:20px 0">
      <div style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.07em;color:#8a8479;margin-bottom:10px">Quick details</div>
      <table cellpadding="0" cellspacing="0" width="100%">
        <tr><td style="font-size:13px;color:#5c574e;padding:3px 0">Role</td><td style="font-size:13px;color:#1a1814;font-weight:500;text-align:right">Founding AI Engineer</td></tr>
        <tr><td style="font-size:13px;color:#5c574e;padding:3px 0">Company</td><td style="font-size:13px;color:#1a1814;font-weight:500;text-align:right">NovaMind</td></tr>
        <tr><td style="font-size:13px;color:#5c574e;padding:3px 0">Location</td><td style="font-size:13px;color:#1a1814;font-weight:500;text-align:right">San Francisco, in-person</td></tr>
        <tr><td style="font-size:13px;color:#5c574e;padding:3px 0">Comp</td><td style="font-size:13px;color:#1a1814;font-weight:500;text-align:right">$150-200k + equity</td></tr>
      </table>
    </div>
    <p style="margin:0 0 24px;font-size:15px;color:#2c2924;line-height:1.6">
      Use the link below to book a 30-minute call directly with the founder:
    </p>
    <table cellpadding="0" cellspacing="0"><tr><td>
      <a href="https://cal.com/novamind" style="display:inline-block;background:#1a1814;color:#fff;text-decoration:none;padding:13px 28px;border-radius:8px;font-size:14px;font-weight:600;letter-spacing:-0.01em">Book founder call &rarr;</a>
    </td></tr></table>
    <p style="margin:28px 0 0;font-size:14px;color:#8a8479;line-height:1.5">
      Talk soon,<br>
      <strong style="color:#2c2924">Ava</strong>, AI recruiting agent
    </p>
  </td></tr>
  <tr><td style="background:#faf8f3;border-top:1px solid #e5dfd2;padding:16px 32px">
    <p style="margin:0;font-size:11px;color:#b5aea0;text-align:center">Sent by Ava, an AI recruiting agent &middot; recagent@agentmail.to</p>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""

    resp = agentmail.send_email(
        to="anishkumar2002.k@gmail.com",
        subject=subject,
        body=body,
        html=html,
    )
    logger.info(f"Demo follow-up email sent: {resp}")
    return {"ok": True, "message_id": resp.get("message_id")}


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
