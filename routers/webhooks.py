"""
Webhook handlers for AgentPhone and AgentMail events.

AgentPhone events:
  - agent.call_ended  → transcript arrives, Gemini processes it, triggers next step

AgentMail events:
  - message.received  → candidate replied to follow-up (log it)
"""
import logging
from fastapi import APIRouter, Request, BackgroundTasks, HTTPException

from agents import gemini
import db
from services import agentmail
from config import settings

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


# ── AgentPhone ─────────────────────────────────────────────────────────────────

@router.post("/agentphone")
async def agentphone_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive AgentPhone events."""
    payload = await request.json()
    event_type = payload.get("event") or payload.get("type", "")
    logger.info(f"AgentPhone event: {event_type}")

    if event_type == "agent.call_ended":
        background_tasks.add_task(_handle_call_ended, payload)

    return {"ok": True}


async def _handle_call_ended(payload: dict):
    """Process a completed call in the background."""
    agentphone_call_id = payload.get("call_id") or payload.get("id", "")
    transcript = payload.get("transcript", "")
    duration = payload.get("duration_seconds") or payload.get("duration", 0)

    call_record = db.get_call_by_agentphone_id(agentphone_call_id)
    if not call_record:
        logger.warning(f"No call record found for agentphone_call_id={agentphone_call_id}")
        return

    call_type = call_record.get("call_type")

    if call_type == "intake":
        await _process_intake_call(call_record, transcript, duration)
    elif call_type == "screening":
        await _process_screening_call(call_record, transcript, duration)


async def _process_intake_call(call_record: dict, transcript: str, duration: int):
    """Extract role brief from founder intake call, load candidates, call top candidate."""
    role_id = call_record["role_id"]
    role = db.get_role(role_id)

    logger.info(f"Processing intake call for role {role_id}")

    # Extract structured brief from transcript
    brief = gemini.extract_role_brief(transcript)
    brief["id"] = role_id

    # Update role with extracted fields
    db.get_db().table("roles").update({
        "title": brief.get("title"),
        "company": brief.get("company"),
        "location": brief.get("location"),
        "must_haves": brief.get("must_haves", []),
        "nice_haves": brief.get("nice_haves", []),
        "comp_range": brief.get("comp_range"),
        "target_background": brief.get("target_background"),
        "dealbreakers": brief.get("dealbreakers"),
        "booking_link": brief.get("booking_link"),
        "raw_transcript": transcript,
    }).eq("id", role_id).execute()

    db.update_call(call_record["id"], status="completed", transcript=transcript, duration_seconds=duration)

    # Load pre-cached candidates and insert into DB
    import json, os
    candidates_path = os.path.join(os.path.dirname(__file__), "..", "data", "candidates.json")
    with open(candidates_path) as f:
        cached = json.load(f)

    inserted = db.insert_candidates(role_id, cached)
    logger.info(f"Inserted {len(inserted)} candidates for role {role_id}")

    # Call the top candidate (highest fit_score)
    top = max(inserted, key=lambda c: c.get("fit_score", 0))
    logger.info(f"Top candidate: {top['name']} ({top['fit_score']}% fit)")

    await _initiate_screening_call(top, brief)


async def _process_screening_call(call_record: dict, transcript: str, duration: int):
    """Summarize screening call, update candidate status, send follow-up email if qualified."""
    candidate_id = call_record.get("candidate_id")
    role_id = call_record["role_id"]

    role = db.get_role(role_id)
    candidate = db.get_db().table("candidates").select("*").eq("id", candidate_id).single().execute().data

    # Detect voicemail / no answer
    if not transcript or len(transcript.strip()) < 20:
        outcome = "voicemail"
        summary = "Candidate did not answer. Voicemail left."
        db.update_call(call_record["id"], status="voicemail", transcript=transcript,
                       outcome="voicemail", duration_seconds=duration, summary=summary)
        db.update_candidate_status(candidate_id, "rejected")
        logger.info(f"Voicemail for {candidate['name']}")
        return

    result = gemini.summarize_screening_call(transcript, role, candidate["name"])
    outcome = result.get("outcome", "rejected")
    summary = result.get("summary", "")

    db.update_call(call_record["id"], status="completed", transcript=transcript,
                   outcome=outcome, duration_seconds=duration, summary=summary)

    new_status = "qualified" if outcome == "qualified" else "rejected"
    db.update_candidate_status(candidate_id, new_status)

    logger.info(f"Candidate {candidate['name']} → {new_status}")

    # Send follow-up email if qualified and interested
    if result.get("send_followup") and candidate.get("email"):
        email_content = gemini.draft_followup_email(role, candidate)
        resp = agentmail.send_email(
            to=candidate["email"],
            subject=email_content["subject"],
            body=email_content["body"],
        )
        db.create_email(
            candidate_id=candidate_id,
            role_id=role_id,
            to_email=candidate["email"],
            subject=email_content["subject"],
            body=email_content["body"],
            agentmail_id=resp.get("message_id"),
        )
        logger.info(f"Follow-up email sent to {candidate['name']} ({candidate['email']})")


async def _initiate_screening_call(candidate: dict, role_brief: dict):
    """Make an outbound call to a candidate."""
    from services.agentphone import make_call

    script = gemini.generate_screening_script(role_brief, candidate)
    call_record = db.create_call(
        call_type="screening",
        role_id=role_brief.get("id", ""),
        candidate_id=candidate["id"],
    )

    db.update_candidate_status(candidate["id"], "calling")

    try:
        call_resp = make_call(
            to_phone=candidate["phone"],
            system_prompt=script,
            initial_greeting=(
                f"Hi {candidate['name'].split()[0]}, this is Ava from HyperVelocity. "
                f"I'm reaching out about a {role_brief.get('title')} role at an early-stage AI startup "
                f"in {role_brief.get('location', 'San Francisco')}. Do you have 30 seconds?"
            ),
        )
        db.update_call(call_record["id"], agentphone_call_id=call_resp.get("id") or call_resp.get("call_id"))
        logger.info(f"Outbound call initiated to {candidate['name']}")
    except Exception as e:
        logger.error(f"Failed to initiate call to {candidate['name']}: {e}")
        db.update_call(call_record["id"], status="failed")


# ── AgentMail ──────────────────────────────────────────────────────────────────

@router.post("/agentmail")
async def agentmail_webhook(request: Request):
    """Receive AgentMail events (candidate replies)."""
    payload = await request.json()
    event_type = payload.get("event_type", "")

    if event_type == "message.received":
        data = payload.get("data", {})
        logger.info(f"Email reply from {data.get('from')} — subject: {data.get('subject')}")
        # Future: auto-reply or notify founder

    return {"ok": True}
